"""Leader Bridge — Coze 插件 ↔ ADP 发现 + 动态路由 Partner"""
import json
import os
import ssl
import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from http.server import HTTPServer, BaseHTTPRequestHandler

import uuid
import time
import threading
from urllib.parse import unquote

LEADER_AIC = "1.2.156.3088.0001.00001.B08ERU.S4IY32.1.002I"
DISCOVERY_URL = "http://117.74.66.90:8005/acps-adp-v2/discover"
FOOTPRINT_URL = "http://117.74.66.90:8006/notify"

_CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ca")
_MTLS_CERT = (os.path.join(_CERT_DIR, "certs", f"{LEADER_AIC}.pem"),
              os.path.join(_CERT_DIR, "private", f"{LEADER_AIC}.key"))
_MTLS_VERIFY = os.path.join(_CERT_DIR, "certs", "trust-bundle.pem")

# ── mTLS Session（HTTPS 请求用，自带客户端证书 + CA 验证，跳过主机名检查）──
_MTLS_SESSION = None

def _mtls_session():
    global _MTLS_SESSION
    if _MTLS_SESSION is None:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.load_cert_chain(_MTLS_CERT[0], _MTLS_CERT[1])
        ctx.load_verify_locations(cafile=_MTLS_VERIFY)
        ctx.check_hostname = False

        class _MtlsAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs["ssl_context"] = ctx
                kwargs["assert_hostname"] = False
                return super().init_poolmanager(*args, **kwargs)

        s = requests.Session()
        s.mount("https://", _MtlsAdapter())
        _MTLS_SESSION = s
    return _MTLS_SESSION

def _post(url, json, timeout=30):
    """发送 POST：HTTPS 走 mTLS Session，HTTP 明文"""
    if url.startswith("https://"):
        return _mtls_session().post(url, json=json, timeout=timeout)
    return requests.post(url, json=json, timeout=timeout)

def _aip_request(agent_url: str, message: str, session_id: str, caller_name: str, caller_aic: str) -> dict:
    """用 AIP JSON-RPC 格式调 Partner，轮询等结果"""
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    req = {
        "jsonrpc": "2.0",
        "id": f"req-{task_id}",
        "method": "task/execute",
        "params": {
            "caller_name": caller_name,
            "caller_aic": caller_aic,
            "command": {
                "taskId": task_id,
                "sessionId": session_id,
                "command": "start",
                "dataItems": [{"text": message}],
            },
        },
    }
    resp = _post(agent_url, req)
    result = resp.json().get("result", {})

    # 轮询等异步返回（0.5s×80=40s，后台慢慢等）
    for _ in range(80):
        state = result.get("status", {}).get("state", "")
        if state in ("awaiting_completion", "completed", "failed", "rejected"):
            break
        time.sleep(0.5)
        poll_req = {
            "jsonrpc": "2.0",
            "id": f"poll-{task_id}",
            "method": "task/execute",
            "params": {
                "command": {
                    "taskId": task_id,
                    "command": "get",
                },
            },
        }
        poll_resp = _post(agent_url, poll_req, 5)
        result = poll_resp.json().get("result", result)

    # 发送 Complete
    _post(agent_url, {
        "jsonrpc": "2.0",
        "id": f"complete-{task_id}",
        "method": "task/execute",
        "params": {"command": {"taskId": task_id, "command": "complete"}},
    }, 10)

    return result

# 本地 Partner 地址（ADP 返回的 endpoint 指向 bridge 自身时，转成本地直连）
LOCAL_PARTNERS = {
    "北邮校园外卖小助手": "https://127.0.0.1:8088",
    "快递小助手": "https://127.0.0.1:8089",
    "天气穿搭管家": "https://127.0.0.1:8090",
    "约会规划师": "https://127.0.0.1:8091",
}

# 异步任务存储: task_id → {"status": "working"|"done", "reply": "...", "aip_result": {...}}
_task_store = {}
_task_lock = threading.Lock()

# ADP 搜索结果缓存: {agent_name: {"aic": ..., "endpoint": ..., "acs": {...}}}
_agent_cache = {}


def _extract_reply(result: dict) -> str:
    """从 AIP TaskResult 中提取文本回复"""
    for prod in result.get("products", []):
        for item in prod.get("dataItems", []):
            if item.get("text"):
                return item["text"]
    for item in result.get("status", {}).get("dataItems", []):
        if item.get("text"):
            return item["text"]
    return ""


class BridgeHandler(BaseHTTPRequestHandler):
    def _reply(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _cache_from_acs_map(self, acs_map):
        """从 ADP 返回的 acsMap 提取名称→地址的映射（同名时优先保留自己的 ngrok 地址）"""
        for aic, acs in acs_map.items():
            name = acs.get("name", "")
            endpoints = acs.get("endPoints", [])
            url = endpoints[0]["url"] if endpoints else ""

            existing = _agent_cache.get(name, {})
            old_url = existing.get("endpoint", "")
            # 同名已有缓存且新 URL 不是自己的 ngrok → 跳过（保留旧缓存）
            if existing and not url.startswith("https://hesitancy-harddisk-tribesman"):
                continue

            _agent_cache[name] = {"aic": aic, "endpoint": url, "acs": acs}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            print(f"[JSON解析失败] path={self.path}, raw={raw[:200]}")
            body = {}
        path = self.path.strip("/")

        if path == "ping":
            self._reply(200, {"status": "ok"})

        elif path == "search":
            try:
                resp = requests.post(
                    DISCOVERY_URL,
                    json={
                        "type": "exploratory",
                        "query": body.get("query", ""),
                        "limit": 5,
                    },
                    timeout=10,
                )
                result = resp.json()
                # 缓存结果
                acs_map = result.get("result", {}).get("acsMap", {})
                self._cache_from_acs_map(acs_map)
                print(f"[缓存] 已缓存 {len(_agent_cache)} 个智能体: {list(_agent_cache.keys())}")
                self._reply(200, result)
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path.startswith("partner/"):
            # 公网直连入口: POST /partner/北邮校园外卖小助手  (AIP JSON-RPC)
            agent_name = unquote(path.replace("partner/", "").strip())
            agent_url = LOCAL_PARTNERS.get(agent_name)
            if not agent_url:
                self._reply(404, {"error": f"未知智能体: {agent_name}"})
                return
            try:
                msg = body.get("message", "") or (body.get("params", {}).get("command", {}).get("dataItems", [{}])[0].get("text", ""))
                sid = body.get("session_id", "") or body.get("params", {}).get("command", {}).get("sessionId", "default")
                result = _aip_request(agent_url, msg, sid, "外部调用", "")
                reply = _extract_reply(result)
                print(f"[公网直连] {agent_name} → {agent_url}")
                self._reply(200, {"reply": reply, "aip_result": result})
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path == "call":
            agent_name = body.get("agent", "")
            message = body.get("message", "")
            session_id = body.get("session_id", "default")
            print(f"[收到call] agent={agent_name}, message={message[:50] if message else ''}, session={session_id}")

            cached = _agent_cache.get(agent_name, {})
            agent_url = cached.get("endpoint", "")
            if not agent_url or "hesitancy-harddisk-tribesman.ngrok-free.dev" in agent_url:
                agent_url = LOCAL_PARTNERS.get(agent_name, "")
            if not agent_url:
                self._reply(404, {"error": f"未知智能体: {agent_name}", "cached": list(_agent_cache.keys())})
                return

            task_id = uuid.uuid4().hex[:8]
            caller_aic = body.get("caller_aic") or LEADER_AIC
            dst_aic = cached.get("aic", "")

            with _task_lock:
                _task_store[task_id] = {"status": "working", "reply": "", "aip_result": None}

            def _do_call():
                try:
                    try:
                        requests.post(FOOTPRINT_URL, json={
                            "AgentName_src": "北邮个人助手", "src_AIC": caller_aic,
                            "AgentName_dist": agent_name, "dest_AIC": dst_aic,
                        }, timeout=5)
                    except Exception:
                        pass
                    result = _aip_request(agent_url, message, session_id, "北邮个人助手", caller_aic)
                    reply = _extract_reply(result)
                    state = result.get("status", {}).get("state", "?")
                    prods = result.get("products", [])
                    print(f"[调用完成] {agent_name} state={state} products={len(prods)} reply_len={len(reply)}")
                    with _task_lock:
                        _task_store[task_id] = {"status": "done", "reply": reply, "aip_result": result}
                except Exception as e:
                    import traceback
                    print(f"[调用失败] {agent_name} → {agent_url}, error={e}")
                    traceback.print_exc()
                    with _task_lock:
                        _task_store[task_id] = {"status": "error", "reply": str(e), "aip_result": None}

            threading.Thread(target=_do_call, daemon=True).start()
            self._reply(200, {"task_id": task_id, "status": "started", "message": "任务已启动，请轮询 /poll 获取结果"})

        elif path == "poll":
            task_id = body.get("task_id", "")
            with _task_lock:
                task = _task_store.get(task_id)
            if not task:
                self._reply(404, {"error": "任务不存在", "task_id": task_id})
                return
            self._reply(200, {
                "task_id": task_id,
                "status": task["status"],
                "reply": task["reply"],
                "aip_result": task.get("aip_result"),
            })

        elif path == "footprint":
            try:
                dst_name = body.get("dst_name", "")
                cached = _agent_cache.get(dst_name, {})
                requests.post(
                    FOOTPRINT_URL,
                    json={
                        "AgentName_src": body.get("src_name", "北邮个人助手"),
                        "src_AIC": body.get("src_aic") or LEADER_AIC,
                        "AgentName_dist": dst_name,
                        "dest_AIC": body.get("dst_aic") or cached.get("aic", ""),
                    },
                    timeout=5,
                )
                self._reply(200, {"status": "ok"})
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path == "status":
            self._reply(200, {
                "status": "running",
                "cached_agents": list(_agent_cache.keys()),
            })

        else:
            self._reply(404, {"error": "not found"})

    def do_GET(self):
        if self.path.strip("/") == "ping":
            self._reply(200, {"status": "ok"})
            return
        self._reply(200, {
            "status": "running",
            "cached_agents": list(_agent_cache.keys()),
        })

    def log_message(self, format, *args):
        pass


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    server = HTTPServer(("0.0.0.0", port), BridgeHandler)
    print(f"[Leader Bridge] http://0.0.0.0:{port}")
    print(f"  POST /search    → ADP 发现 + 缓存结果")
    print(f"  POST /call      → 动态路由到 Partner")
    print(f"  POST /footprint → 上报大屏")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Leader Bridge] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
