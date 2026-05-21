# Campus ACPs Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web chat interface for the campus ACPs leader assistant, with automatic/manual partner routing and a visible call-chain panel.

**Architecture:** Add a small standard-library Python web server in `web_app.py` that serves static files from `web/` and proxies chat requests to the existing `leader_bridge.py` service. Keep the ACPs/AIP path unchanged: browser -> `web_app.py` -> `leader_bridge.py` -> partner agents.

**Tech Stack:** Python standard library `http.server`, existing `requests`, `unittest`, native HTML/CSS/JavaScript.

---

## File Structure

- Create `web_app.py`: local web server, API routes, intent detection, bridge proxying, response aggregation.
- Create `web/index.html`: three-column workbench UI.
- Create `web/styles.css`: polished campus assistant styling, responsive layout, partner colors.
- Create `web/app.js`: chat state, mode switching, prompt chips, API calls, call-chain rendering.
- Create `tests/test_web_app.py`: unit tests for routing, response aggregation, and API helper behavior.
- Modify `.gitignore`: add `.superpowers/` so visual brainstorming artifacts are not committed.

## Task 1: Routing And Aggregation Core

**Files:**
- Create: `web_app.py`
- Create: `tests/test_web_app.py`

- [ ] **Step 1: Write failing tests for partner detection and reply aggregation**

Create `tests/test_web_app.py` with:

```python
import unittest

import web_app


class RoutingTests(unittest.TestCase):
    def test_detect_agents_matches_multiple_campus_intents(self):
        message = "下午去取快递，顺便吃饭，今天穿什么？"

        agents = web_app.detect_agents(message)

        self.assertEqual(
            agents,
            ["天气穿搭管家", "快递小助手", "北邮校园外卖小助手"],
        )

    def test_detect_agents_matches_date_plan(self):
        message = "下雨天和女朋友在学校附近约会怎么安排？"

        agents = web_app.detect_agents(message)

        self.assertEqual(agents, ["天气穿搭管家", "约会规划师"])

    def test_detect_agents_returns_empty_for_unsupported_message(self):
        message = "帮我办理校园网宽带套餐"

        agents = web_app.detect_agents(message)

        self.assertEqual(agents, [])

    def test_build_combined_reply_keeps_successes_and_failures(self):
        calls = [
            {
                "agent": "天气穿搭管家",
                "ok": True,
                "reply": "今天有雨，建议带伞。",
                "elapsed_ms": 120,
            },
            {
                "agent": "快递小助手",
                "ok": False,
                "error": "连接超时",
                "elapsed_ms": 3000,
            },
        ]

        reply = web_app.build_combined_reply(calls)

        self.assertIn("天气穿搭管家", reply)
        self.assertIn("今天有雨，建议带伞。", reply)
        self.assertIn("快递小助手 暂时不可用", reply)
        self.assertIn("连接超时", reply)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because `web_app.py` does not exist**

Run:

```powershell
python -m unittest tests.test_web_app -v
```

Expected: FAIL or ERROR with `ModuleNotFoundError: No module named 'web_app'`.

- [ ] **Step 3: Implement routing constants and pure helper functions**

Create `web_app.py` with:

```python
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
```

- [ ] **Step 4: Run tests and verify pure helper tests pass**

Run:

```powershell
python -m unittest tests.test_web_app -v
```

Expected: PASS for all tests.

- [ ] **Step 5: Commit routing core**

Run:

```powershell
git add web_app.py tests/test_web_app.py
git commit -m "Add web UI routing core"
```

Expected: commit succeeds.

## Task 2: HTTP API Server

**Files:**
- Modify: `web_app.py`
- Modify: `tests/test_web_app.py`

- [ ] **Step 1: Add failing tests for request payload planning**

Append to `tests/test_web_app.py`:

```python
class ChatPlanningTests(unittest.TestCase):
    def test_plan_chat_uses_manual_selected_agent(self):
        payload = {
            "message": "今天穿什么？",
            "mode": "manual",
            "selected_agent": "天气穿搭管家",
        }

        agents = web_app.plan_agents(payload)

        self.assertEqual(agents, ["天气穿搭管家"])

    def test_plan_chat_rejects_unknown_manual_agent(self):
        payload = {
            "message": "今天穿什么？",
            "mode": "manual",
            "selected_agent": "不存在的智能体",
        }

        with self.assertRaises(ValueError) as ctx:
            web_app.plan_agents(payload)

        self.assertIn("未知智能体", str(ctx.exception))

    def test_plan_chat_uses_auto_detection(self):
        payload = {
            "message": "下午去取快递，今天穿什么？",
            "mode": "auto",
            "selected_agent": "",
        }

        agents = web_app.plan_agents(payload)

        self.assertEqual(agents, ["天气穿搭管家", "快递小助手"])
```

- [ ] **Step 2: Run tests and verify the new tests fail**

Run:

```powershell
python -m unittest tests.test_web_app -v
```

Expected: FAIL with `AttributeError: module 'web_app' has no attribute 'plan_agents'`.

- [ ] **Step 3: Implement planning, bridge calls, and API handler**

Append to `web_app.py`:

```python
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
        relative = request_path.lstrip("/")
        target = (WEB_DIR / relative).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.exists() or target.is_dir():
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
```

- [ ] **Step 4: Run tests and verify all backend tests pass**

Run:

```powershell
python -m unittest tests.test_web_app -v
```

Expected: PASS.

- [ ] **Step 5: Commit API server**

Run:

```powershell
git add web_app.py tests/test_web_app.py
git commit -m "Add campus web API server"
```

Expected: commit succeeds.

## Task 3: Frontend Markup And Styling

**Files:**
- Create: `web/index.html`
- Create: `web/styles.css`

- [ ] **Step 1: Create the HTML shell**

Create `web/index.html` with:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>北邮个人助手 · Campus ACPs Console</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <div class="app-shell">
    <aside class="side-panel">
      <div class="brand">
        <div class="brand-mark">邮</div>
        <div>
          <h1>北邮个人助手</h1>
          <p>Campus ACPs Console</p>
        </div>
      </div>

      <section class="panel-section">
        <div class="section-label">调度模式</div>
        <div class="segmented" role="tablist" aria-label="调度模式">
          <button class="segment active" id="mode-auto" data-mode="auto">自动</button>
          <button class="segment" id="mode-manual" data-mode="manual">手动</button>
        </div>
      </section>

      <section class="panel-section">
        <div class="section-label">可调用智能体</div>
        <div class="agent-list" id="agent-list"></div>
      </section>

      <section class="panel-section status-box" id="service-status">
        <div class="section-label">服务状态</div>
        <p>正在检查本地桥接服务...</p>
      </section>
    </aside>

    <main class="chat-panel">
      <header class="chat-header">
        <div>
          <h2>校园生活协同助手</h2>
          <p>输入一个需求，查看主智能体如何调度 Partner。</p>
        </div>
        <span class="session-pill" id="session-pill">session: web-demo</span>
      </header>

      <div class="prompt-row" id="prompt-row"></div>
      <div class="messages" id="messages" aria-live="polite"></div>

      <form class="composer" id="chat-form">
        <input id="message-input" autocomplete="off" placeholder="例如：下午去取快递，顺便吃饭，今天穿什么？">
        <button id="send-button" type="submit">发送</button>
      </form>
    </main>

    <aside class="chain-panel">
      <header>
        <h2>调用链路</h2>
        <p>用户请求 → 北邮个人助手 → 子智能体 → 汇总答复</p>
      </header>
      <div class="chain-list" id="chain-list"></div>
    </aside>
  </div>

  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create responsive styling**

Create `web/styles.css` with:

```css
:root {
  --bg: #eef3f8;
  --panel: #ffffff;
  --line: #d9e2ef;
  --text: #17233a;
  --muted: #627087;
  --blue: #1f6feb;
  --green: #16a34a;
  --amber: #f59e0b;
  --purple: #7c3aed;
  --red: #dc2626;
  font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
}

button,
input {
  font: inherit;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 280px minmax(420px, 1fr) 340px;
  gap: 16px;
  padding: 16px;
}

.side-panel,
.chat-panel,
.chain-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}

.side-panel,
.chain-panel {
  padding: 16px;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
}

.brand-mark {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--blue);
  color: #ffffff;
  font-weight: 700;
}

.brand h1,
.chat-header h2,
.chain-panel h2 {
  margin: 0;
  font-size: 20px;
  line-height: 1.25;
}

.brand p,
.chat-header p,
.chain-panel p,
.status-box p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.panel-section {
  margin-top: 22px;
}

.section-label {
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}

.segmented {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.segment,
.agent-button,
.prompt-chip,
.composer button {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fbff;
  color: var(--text);
  cursor: pointer;
}

.segment {
  padding: 10px;
}

.segment.active,
.composer button {
  background: var(--blue);
  border-color: var(--blue);
  color: #ffffff;
}

.agent-list {
  display: grid;
  gap: 8px;
}

.agent-button {
  padding: 11px;
  text-align: left;
  border-left: 4px solid var(--agent-color, var(--blue));
}

.agent-button.active {
  background: #edf6ff;
  border-color: var(--agent-color, var(--blue));
}

.status-box {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfdff;
}

.status-online {
  color: var(--green);
  font-weight: 700;
}

.status-offline {
  color: var(--red);
  font-weight: 700;
}

.chat-panel {
  display: flex;
  min-height: calc(100vh - 32px);
  overflow: hidden;
  flex-direction: column;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--line);
}

.session-pill {
  align-self: flex-start;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f1f5fb;
  color: var(--muted);
  font-size: 12px;
}

.prompt-row {
  display: flex;
  gap: 8px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--line);
  overflow-x: auto;
}

.prompt-chip {
  flex: 0 0 auto;
  padding: 8px 10px;
  font-size: 13px;
}

.messages {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  overflow-y: auto;
}

.message {
  max-width: 82%;
  padding: 12px 14px;
  border-radius: 8px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.message.user {
  align-self: flex-start;
  background: #f1f5fb;
}

.message.assistant {
  align-self: flex-end;
  background: var(--blue);
  color: #ffffff;
}

.message.error {
  align-self: flex-end;
  background: #fff1f2;
  color: #991b1b;
  border: 1px solid #fecdd3;
}

.composer {
  display: flex;
  gap: 10px;
  padding: 14px;
  border-top: 1px solid var(--line);
}

.composer input {
  flex: 1;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.composer button {
  min-width: 84px;
  padding: 0 16px;
}

.composer button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.chain-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.chain-item {
  padding: 11px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfdff;
}

.chain-topline {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 14px;
}

.chain-status {
  font-size: 12px;
  font-weight: 700;
}

.chain-status.done {
  color: var(--green);
}

.chain-status.failed {
  color: var(--red);
}

.chain-status.warning {
  color: var(--amber);
}

.chain-meta {
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 1080px) {
  .app-shell {
    grid-template-columns: 240px 1fr;
  }

  .chain-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .app-shell {
    grid-template-columns: 1fr;
    padding: 10px;
  }

  .chat-panel {
    min-height: 70vh;
  }

  .chat-header,
  .composer {
    flex-direction: column;
  }

  .message {
    max-width: 100%;
  }
}
```

- [ ] **Step 3: Start server and check static files manually**

Run:

```powershell
python web_app.py
```

Expected output contains:

```text
[Campus ACPs Web UI] http://127.0.0.1:5000
```

Open `http://127.0.0.1:5000` in a browser. Expected: page loads with left panel, chat panel, and call-chain panel.

- [ ] **Step 4: Commit frontend shell**

Run:

```powershell
git add web/index.html web/styles.css
git commit -m "Add campus web UI shell"
```

Expected: commit succeeds.

## Task 4: Frontend Behavior

**Files:**
- Create: `web/app.js`

- [ ] **Step 1: Create frontend JavaScript**

Create `web/app.js` with:

```javascript
const state = {
  mode: "auto",
  selectedAgent: "",
  sessionId: "web-demo",
  agents: [],
  demoPrompts: [],
  sending: false,
};

const els = {
  modeAuto: document.querySelector("#mode-auto"),
  modeManual: document.querySelector("#mode-manual"),
  agentList: document.querySelector("#agent-list"),
  serviceStatus: document.querySelector("#service-status"),
  promptRow: document.querySelector("#prompt-row"),
  messages: document.querySelector("#messages"),
  chainList: document.querySelector("#chain-list"),
  form: document.querySelector("#chat-form"),
  input: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
};

function setMode(mode) {
  state.mode = mode;
  els.modeAuto.classList.toggle("active", mode === "auto");
  els.modeManual.classList.toggle("active", mode === "manual");
  renderAgents();
}

function renderAgents() {
  els.agentList.innerHTML = "";
  state.agents.forEach((agent) => {
    const button = document.createElement("button");
    button.className = "agent-button";
    button.style.setProperty("--agent-color", agent.accent);
    button.textContent = agent.name;
    button.title = agent.description;
    button.classList.toggle("active", state.selectedAgent === agent.name);
    button.addEventListener("click", () => {
      state.selectedAgent = agent.name;
      setMode("manual");
    });
    els.agentList.appendChild(button);
  });
}

function renderPrompts() {
  els.promptRow.innerHTML = "";
  state.demoPrompts.forEach((prompt) => {
    const button = document.createElement("button");
    button.className = "prompt-chip";
    button.textContent = prompt;
    button.addEventListener("click", () => {
      els.input.value = prompt;
      els.input.focus();
    });
    els.promptRow.appendChild(button);
  });
}

function renderStatus(bridge) {
  const online = bridge && bridge.online;
  els.serviceStatus.innerHTML = `
    <div class="section-label">服务状态</div>
    <p class="${online ? "status-online" : "status-offline"}">
      ${online ? "leader_bridge.py 在线" : "leader_bridge.py 未连接"}
    </p>
    <p>${online ? "可以开始演示多智能体调用。" : "请先运行：python leader_bridge.py"}</p>
  `;
}

function appendMessage(role, text, extraClass = "") {
  const message = document.createElement("div");
  message.className = `message ${role} ${extraClass}`.trim();
  message.textContent = text;
  els.messages.appendChild(message);
  els.messages.scrollTop = els.messages.scrollHeight;
  return message;
}

function renderChain(chain) {
  els.chainList.innerHTML = "";
  const items = chain && chain.length ? chain : [
    { label: "等待用户请求", status: "warning" },
  ];

  items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "chain-item";
    const statusText = {
      done: "完成",
      failed: "失败",
      warning: "等待",
    }[item.status] || item.status;
    const elapsed = item.elapsed_ms ? `<div class="chain-meta">${item.elapsed_ms} ms</div>` : "";
    row.innerHTML = `
      <div class="chain-topline">
        <span>${index + 1}. ${item.label}</span>
        <span class="chain-status ${item.status}">${statusText}</span>
      </div>
      ${elapsed}
    `;
    els.chainList.appendChild(row);
  });
}

function setSending(sending) {
  state.sending = sending;
  els.sendButton.disabled = sending;
  els.input.disabled = sending;
  els.sendButton.textContent = sending ? "调用中" : "发送";
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    state.agents = data.agents || [];
    state.demoPrompts = data.demo_prompts || [];
    if (!state.selectedAgent && state.agents.length) {
      state.selectedAgent = state.agents[0].name;
    }
    renderAgents();
    renderPrompts();
    renderStatus(data.bridge);
    renderChain([]);
  } catch (error) {
    renderStatus({ online: false, error: String(error) });
  }
}

async function sendMessage(message) {
  appendMessage("user", message);
  const pending = appendMessage("assistant", "正在分析需求并调度校园智能体...");
  renderChain([
    { label: "用户请求", status: "done" },
    { label: "北邮个人助手解析意图", status: "warning" },
  ]);

  setSending(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode: state.mode,
        selected_agent: state.selectedAgent,
        session_id: state.sessionId,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || "请求失败");
    }
    pending.textContent = data.reply;
    renderChain(data.chain);
  } catch (error) {
    pending.classList.remove("assistant");
    pending.classList.add("error");
    pending.textContent = `调用失败：${error.message}`;
    renderChain([
      { label: "用户请求", status: "done" },
      { label: "北邮个人助手", status: "failed" },
    ]);
  } finally {
    setSending(false);
    els.input.focus();
  }
}

els.modeAuto.addEventListener("click", () => setMode("auto"));
els.modeManual.addEventListener("click", () => setMode("manual"));

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = els.input.value.trim();
  if (!message || state.sending) return;
  els.input.value = "";
  sendMessage(message);
});

loadStatus();
```

- [ ] **Step 2: Manual browser test with bridge offline**

Run:

```powershell
python web_app.py
```

Open `http://127.0.0.1:5000` while `leader_bridge.py` is not running.

Expected:

- Left status shows `leader_bridge.py 未连接`.
- Sending a message returns a visible failure or unavailable response.
- Page remains usable.

- [ ] **Step 3: Commit frontend behavior**

Run:

```powershell
git add web/app.js
git commit -m "Add campus web UI behavior"
```

Expected: commit succeeds.

## Task 5: Runtime Verification And Documentation Touches

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add visual companion artifacts to `.gitignore`**

Append this section to `.gitignore`:

```gitignore
# Superpowers brainstorming artifacts
.superpowers/
```

- [ ] **Step 2: Run unit tests**

Run:

```powershell
python -m unittest tests.test_web_app -v
```

Expected: all tests pass.

- [ ] **Step 3: Start the full local demo stack**

Open separate PowerShell terminals and run:

```powershell
cd D:\ACPs
python food_agent\main.py
```

```powershell
cd D:\ACPs
python express_agent\main.py
```

```powershell
cd D:\ACPs
python weather_agent\main.py
```

```powershell
cd D:\ACPs
python date_agent\main.py
```

```powershell
cd D:\ACPs
python leader_bridge.py
```

```powershell
cd D:\ACPs
python web_app.py
```

Expected:

- Partner agents print their AIP server URLs.
- `leader_bridge.py` prints `http://0.0.0.0:8766`.
- `web_app.py` prints `http://127.0.0.1:5000`.

- [ ] **Step 4: Verify API status**

Run:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/status" -UseBasicParsing
```

Expected:

- HTTP 200.
- JSON contains `"online": true` under `"bridge"` when `leader_bridge.py` is running.

- [ ] **Step 5: Verify automatic multi-agent demo**

Open `http://127.0.0.1:5000`, click the prompt:

```text
下午去取快递，顺便吃饭，今天穿什么？
```

Expected:

- Chat shows a user message.
- Assistant reply contains sections for weather, express, and food.
- Right call-chain contains `天气穿搭管家`, `快递小助手`, and `北邮校园外卖小助手`.

- [ ] **Step 6: Verify manual single-agent demo**

In the page:

- Click `手动`.
- Click `天气穿搭管家`.
- Send:

```text
今天去上课穿什么？
```

Expected:

- Only `天气穿搭管家` appears as a partner node in the call chain.
- Assistant reply contains only the weather partner result.

- [ ] **Step 7: Commit final verification support**

Run:

```powershell
git add .gitignore
git commit -m "Ignore brainstorming artifacts"
```

Expected: commit succeeds if `.gitignore` changed.

## Self-Review

- Spec coverage: the plan covers local web serving, automatic and manual routing, visible call-chain steps, demo prompts, bridge status, partner failure handling, frontend layout, and verification.
- Red-flag scan: no unresolved markers or unspecified implementation steps remain.
- Type consistency: backend payload names are `message`, `mode`, `selected_agent`, and `session_id`; frontend uses the same names. Backend response keys are `ok`, `agents`, `calls`, `chain`, and `reply`; frontend reads those same keys.
