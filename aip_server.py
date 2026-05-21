"""AIP 协议 RPC 服务端 — 任务生命周期管理 + Coze 集成"""
import json
import logging
import ssl
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from aip_models import (
    TaskState, TaskCommandType, TaskStatus, TaskResult, Product,
    TextDataItem, now_iso,
)

logger = logging.getLogger("aip_server")


class AipTaskManager:
    """管理 AIP 任务状态机"""

    def __init__(self, agent_name: str, agent_aic: str, coze_client, footprint_callback=None):
        self.agent_name = agent_name
        self.agent_aic = agent_aic
        self.coze = coze_client
        self.footprint_callback = footprint_callback
        self.tasks: dict = {}  # taskId → TaskResult
        self._lock = threading.Lock()

    def handle_command(self, command_dict: dict, caller_name: str = "", caller_aic: str = "") -> TaskResult:
        cmd_type = command_dict.get("command", "start")
        task_id = command_dict.get("taskId", "")
        session_id = command_dict.get("sessionId", "")
        data_items = command_dict.get("dataItems", [])

        if cmd_type == TaskCommandType.Start.value:
            return self._on_start(task_id, session_id, data_items, caller_name, caller_aic)
        elif cmd_type == TaskCommandType.Get.value:
            return self._on_get(task_id)
        elif cmd_type == TaskCommandType.Continue.value:
            return self._on_continue(task_id, data_items)
        elif cmd_type == TaskCommandType.Cancel.value:
            return self._on_cancel(task_id)
        elif cmd_type == TaskCommandType.Complete.value:
            return self._on_complete(task_id)
        else:
            return self._make_result(task_id, session_id,
                TaskStatus(state=TaskState.Failed, dataItems=[TextDataItem(text=f"Unknown command: {cmd_type}")]))

    def _extract_text(self, data_items: list) -> str:
        texts = []
        for item in data_items:
            if isinstance(item, dict):
                texts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                texts.append(item.text)
        return "\n".join(texts)

    def _make_result(self, task_id: str, session_id: str, status: TaskStatus, products: list = None) -> TaskResult:
        result = TaskResult(
            id=f"result-{task_id}",
            senderId=self.agent_name,
            taskId=task_id,
            sessionId=session_id,
            status=status,
            products=products or [],
            statusHistory=[status],
        )
        with self._lock:
            self.tasks[task_id] = result
        return result

    def _on_start(self, task_id: str, session_id: str, data_items: list, caller_name: str, caller_aic: str) -> TaskResult:
        logger.info(f"[{self.agent_name}] Start task={task_id}")

        # 提取用户消息
        user_message = self._extract_text(data_items)

        # 异步调用 Coze
        def run_coze():
            try:
                reply = self.coze.chat(user_id=session_id or task_id, message=user_message or "你好")
            except Exception as e:
                reply = f"[Coze错误] {e}"
            with self._lock:
                task = self.tasks.get(task_id)
                if task:
                    task.status = TaskStatus(
                        state=TaskState.AwaitingCompletion,
                        dataItems=[TextDataItem(text="任务完成，请查看结果")],
                    )
                    task.products = [Product(id=f"prod-{task_id}", dataItems=[TextDataItem(text=reply)])]
                    logger.info(f"[{self.agent_name}] Task {task_id} → AwaitingCompletion")

        threading.Thread(target=run_coze, daemon=True).start()

        return self._make_result(task_id, session_id,
            TaskStatus(state=TaskState.Working))

    def _on_get(self, task_id: str) -> TaskResult:
        with self._lock:
            task = self.tasks.get(task_id)
            if task:
                logger.info(f"[{self.agent_name}] Get task={task_id} state={task.status.state.value}")
                return task
        logger.warning(f"[{self.agent_name}] Get task={task_id} NOT FOUND")
        return TaskResult(
            id=f"result-{task_id}",
            taskId=task_id,
            status=TaskStatus(state=TaskState.Failed, dataItems=[TextDataItem(text="Task not found")]),
        )

    def _on_continue(self, task_id: str, data_items: list) -> TaskResult:
        user_message = self._extract_text(data_items)
        logger.info(f"[{self.agent_name}] Continue task={task_id}: {user_message[:50]}")

        def run_coze_continue():
            try:
                reply = self.coze.chat(user_id=task_id, message=user_message)
            except Exception as e:
                reply = f"[Coze错误] {e}"
            with self._lock:
                task = self.tasks.get(task_id)
                if task:
                    task.status = TaskStatus(state=TaskState.AwaitingCompletion,
                        dataItems=[TextDataItem(text="任务完成")])
                    task.products = [Product(id=f"prod-{task_id}", dataItems=[TextDataItem(text=reply)])]

        threading.Thread(target=run_coze_continue, daemon=True).start()

        return self._make_result(task_id, "",
            TaskStatus(state=TaskState.Working, dataItems=[TextDataItem(text="正在处理补充信息...")]))

    def _on_cancel(self, task_id: str) -> TaskResult:
        logger.info(f"[{self.agent_name}] Cancel task={task_id}")
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status.state not in (TaskState.Completed, TaskState.Failed, TaskState.Rejected, TaskState.Canceled):
                task.status = TaskStatus(state=TaskState.Canceled)
        return self._on_get(task_id)

    def _on_complete(self, task_id: str) -> TaskResult:
        logger.info(f"[{self.agent_name}] Complete task={task_id}")
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status.state == TaskState.AwaitingCompletion:
                task.status = TaskStatus(state=TaskState.Completed)
        return self._on_get(task_id)


class AipHttpHandler(BaseHTTPRequestHandler):
    """AIP JSON-RPC HTTP 处理器"""
    task_manager: AipTaskManager = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        path = self.path.strip("/")

        if path == "rpc" or path == "" or path.startswith("partner/"):
            # AIP JSON-RPC 格式
            rpc_id = body.get("id", "")
            params = body.get("params", {})
            command = params.get("command", params)  # 兼容有/无 params 包裹

            caller_name = body.get("caller_name", params.get("caller_name", ""))
            caller_aic = body.get("caller_aic", params.get("caller_aic", ""))

            result = self.task_manager.handle_command(command, caller_name, caller_aic)

            self._reply(200, {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": self._to_dict(result),
            })
        else:
            self._reply(404, {"error": "not found"})

    def do_GET(self):
        path = self.path.strip("/")
        if path == "health" or path == "":
            self._reply(200, {"status": "ok", "agent": self.task_manager.agent_name})
        elif path == ".well-known/acs.json":
            self._reply(200, {})
        else:
            self._reply(404, {"error": "not found"})

    def _reply(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _to_dict(self, obj) -> dict:
        """dataclass → dict"""
        if hasattr(obj, "__dataclass_fields__"):
            result = {}
            for f in obj.__dataclass_fields__:
                val = getattr(obj, f)
                if isinstance(val, list):
                    val = [self._to_dict(v) if hasattr(v, "__dataclass_fields__") else v for v in val]
                elif hasattr(val, "__dataclass_fields__"):
                    val = self._to_dict(val)
                elif isinstance(val, type(TaskState.Accepted)):
                    val = val.value
                result[f] = val
            return result
        return obj

    def log_message(self, format, *args):
        pass


def create_aip_server(agent_name: str, agent_aic: str, coze_client,
                      footprint_callback=None, port: int = 8088,
                      cert_path: str = "", key_path: str = "", ca_bundle_path: str = ""):
    """创建 AIP 服务实例
    当提供 cert_path/key_path 时启用 HTTPS + mTLS。
    """
    manager = AipTaskManager(agent_name, agent_aic, coze_client, footprint_callback)
    handler = type("Handler", (AipHttpHandler,), {"task_manager": manager})
    server = HTTPServer(("0.0.0.0", port), handler)

    if cert_path and key_path:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_path, key_path)
        if ca_bundle_path:
            ctx.load_verify_locations(cafile=ca_bundle_path)
            ctx.verify_mode = ssl.CERT_REQUIRED
        server.socket = ctx.wrap_socket(server.socket, server_side=True)

    return server
