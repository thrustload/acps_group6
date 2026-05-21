"""Local web UI for the campus ACPs multi-agent demo."""
from __future__ import annotations

import json
import mimetypes
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

HOST = "127.0.0.1"
PORT = 5000
BRIDGE_BASE_URL = "http://127.0.0.1:8766"
ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"

AGENTS = [
    {
        "name": "天气穿搭管家",
        "domain": "weather",
        "accent": "#1f6feb",
        "description": "查询校园天气并给出穿搭、带伞、通勤建议。",
    },
    {
        "name": "快递小助手",
        "domain": "express",
        "accent": "#f59e0b",
        "description": "查询快递物流状态并规划校园取件时间。",
    },
    {
        "name": "北邮校园外卖小助手",
        "domain": "food",
        "accent": "#16a34a",
        "description": "查询食堂菜单、外卖下单和配送状态。",
    },
    {
        "name": "约会规划师",
        "domain": "date",
        "accent": "#7c3aed",
        "description": "规划校园周边餐厅、电影和约会动线。",
    },
]

KEYWORDS = {
    "天气穿搭管家": [
        "weather", "temperature", "rain", "wind", "cold", "hot", "outfit", "umbrella",
        "天气", "下雨", "温度", "穿", "穿搭", "带伞", "冷", "热", "刮风",
    ],
    "快递小助手": [
        "express", "package", "logistics", "tracking", "pickup",
        "快递", "物流", "单号", "取件", "驿站", "到哪",
    ],
    "北邮校园外卖小助手": [
        "food", "canteen", "delivery", "order", "meal",
        "吃", "外卖", "食堂", "菜单", "点餐", "下单", "晚饭", "午饭",
    ],
    "约会规划师": [
        "date", "restaurant", "movie", "plan",
        "约会", "餐厅", "电影", "规划", "女朋友", "男朋友", "情侣",
    ],
}

DEMO_PROMPTS = [
    "下午去取快递，顺便吃饭，今天穿什么？",
    "下雨天和女朋友在学校附近约会怎么安排？",
    "帮我查快递并规划取件时间",
]


@dataclass
class BridgeCall:
    agent: str
    ok: bool
    reply: str = ""
    error: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "ok": self.ok,
            "reply": self.reply,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


def detect_agents(message: str) -> list[str]:
    lowered = message.lower()
    selected = []
    for agent in AGENTS:
        name = agent["name"]
        if any(keyword.lower() in lowered for keyword in KEYWORDS[name]):
            selected.append(name)
    return selected


def build_combined_reply(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return "我还没有识别出明确的校园生活场景。可以试试天气穿搭、快递查询、外卖订餐或约会规划。"

    sections = []
    for call in calls:
        agent = call["agent"]
        if call.get("ok"):
            sections.append(f"【{agent}】\n{call.get('reply', '').strip()}")
        else:
            sections.append(f"【{agent} 暂时不可用】\n原因：{call.get('error', '未知错误')}")
    return "\n\n".join(sections)


def agent_names() -> set[str]:
    return {agent["name"] for agent in AGENTS}


def plan_agents(payload: dict[str, Any]) -> list[str]:
    message = str(payload.get("message", "")).strip()
    mode = str(payload.get("mode", "auto")).strip() or "auto"
    selected_agent = str(payload.get("selected_agent", "")).strip()

    if not message:
        raise ValueError("请输入要咨询的校园生活需求。")

    if mode == "manual":
        if selected_agent not in agent_names():
            raise ValueError(f"未知智能体：{selected_agent}")
        return [selected_agent]

    if mode != "auto":
        raise ValueError(f"未知调度模式：{mode}")

    return detect_agents(message)


def call_bridge(agent: str, message: str, session_id: str) -> BridgeCall:
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{BRIDGE_BASE_URL}/call",
            json={
                "agent": agent,
                "message": message,
                "session_id": session_id or "web-demo",
            },
            timeout=45,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        data = response.json()
        reply = str(data.get("reply", "")).strip()
        if not reply:
            reply = "该智能体已返回，但没有提供文本回复。"
        return BridgeCall(agent=agent, ok=True, reply=reply, elapsed_ms=elapsed_ms)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return BridgeCall(agent=agent, ok=False, error=str(exc), elapsed_ms=elapsed_ms)


def bridge_status() -> dict[str, Any]:
    try:
        response = requests.get(f"{BRIDGE_BASE_URL}/status", timeout=3)
        response.raise_for_status()
        return {"online": True, "detail": response.json()}
    except Exception as exc:
        return {"online": False, "error": str(exc)}


def make_chain(agents: list[str], calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chain = [
        {"label": "用户请求", "status": "done"},
        {"label": "北邮个人助手解析意图", "status": "done" if agents else "warning"},
    ]
    call_by_agent = {call["agent"]: call for call in calls}
    for agent in agents:
        call = call_by_agent.get(agent, {})
        chain.append({
            "label": agent,
            "status": "done" if call.get("ok") else "failed",
            "elapsed_ms": call.get("elapsed_ms", 0),
        })
    chain.append({"label": "汇总答复", "status": "done" if calls else "warning"})
    return chain


def chat_response(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    session_id = str(payload.get("session_id", "web-demo")).strip() or "web-demo"
    agents = plan_agents(payload)

    if not agents:
        calls: list[dict[str, Any]] = []
        return {
            "ok": True,
            "agents": [],
            "calls": calls,
            "chain": make_chain([], calls),
            "reply": build_combined_reply(calls),
        }

    calls = [call_bridge(agent, message, session_id).to_dict() for agent in agents]
    return {
        "ok": any(call["ok"] for call in calls),
        "agents": agents,
        "calls": calls,
        "chain": make_chain(agents, calls),
        "reply": build_combined_reply(calls),
    }


def resolve_static_path(request_path: str) -> Path | None:
    web_root = WEB_DIR.resolve()
    relative = request_path.lstrip("/")
    target = (web_root / relative).resolve()
    try:
        target.relative_to(web_root)
    except ValueError:
        return None

    if not target.exists() or target.is_dir():
        return None
    return target


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._json(200, {
                "bridge": bridge_status(),
                "agents": AGENTS,
                "demo_prompts": DEMO_PROMPTS,
            })
            return

        path = parsed.path
        if path == "/":
            path = "/index.html"
        self._static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/chat":
            self._json(404, {"ok": False, "error": "not found"})
            return

        try:
            payload = self._read_json()
            self._json(200, chat_response(payload))
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)

    def _json(self, status: int, data: dict[str, Any]):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, request_path: str):
        target = resolve_static_path(request_path)
        if target is None:
            self._json(404, {"ok": False, "error": "not found"})
            return

        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or target.suffix == ".js":
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        pass


def main():
    server = HTTPServer((HOST, PORT), WebHandler)
    print(f"[Campus ACPs Web UI] http://{HOST}:{PORT}")
    print("  启动顺序：4 个 partner agent -> leader_bridge.py -> web_app.py")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Campus ACPs Web UI] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
