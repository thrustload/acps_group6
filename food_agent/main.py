"""校园外卖智能体 ACPs 接入主程序"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ACPs_Footprint import ACPs_Footprint
from coze_client import CozeAgent

# ===== 配置 =====
AGENT_NAME = "北邮校园外卖小助手"
COZE_BOT_ID = os.getenv("COZE_BOT_ID", "7641282021083676718")
COZE_TOKEN = os.getenv("COZE_TOKEN", "pat_6B25NnqRVG4SwQeevPp2v46b9uQCTJfMbHctGPNaaPGmYaeKrHs6ynB68780xXOW")
MY_AIC = "1.2.156.3088.0001.00001.4UBXND.RABBX9.1.0ITQ"
DISPLAY_SERVER_URL = "http://117.74.66.90:8006/notify"

coze = CozeAgent(bot_id=COZE_BOT_ID, token=COZE_TOKEN)

ACS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acs.json")
with open(ACS_PATH, "r", encoding="utf-8") as f:
    ACS = json.load(f)


def handle_user_message(user_id: str, message: str) -> str:
    """处理用户消息，调用 Coze 智能体"""
    print(f"[用户 {user_id[:8]}...] {message}")
    reply = coze.chat(user_id=user_id, message=message)
    print(f"[回复] {reply[:100]}...")
    return reply


def notify_to_dashboard(src_name: str, src_aic: str, dst_name: str, dst_aic: str):
    """向态势感知大屏上报流转通知"""
    ACPs_Footprint.notify(
        url=DISPLAY_SERVER_URL,
        AgentName_src=src_name,
        src_AIC=src_aic,
        AgentName_dist=dst_name,
        dest_AIC=dst_aic,
    )


# ===== 简易 HTTP 服务（AIP 入口） =====
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class AIPHandler(BaseHTTPRequestHandler):
    """AIP 协议请求处理"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body)

        # 上报大屏（被调用时）
        caller_name = data.get("caller_name", "未知智能体")
        caller_aic = data.get("caller_aic", "未知")
        notify_to_dashboard(caller_name, caller_aic, AGENT_NAME, MY_AIC)

        # 提取用户消息，转发给 Coze
        user_message = data.get("message", "")
        user_id = data.get("session_id", "default")
        reply = handle_user_message(user_id, user_message)

        result = {
            "status": "completed",
            "agent": AGENT_NAME,
            "aic": MY_AIC,
            "reply": reply,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())

    def do_GET(self):
        """健康检查 + ACS 获取"""
        if self.path == "/.well-known/acs.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(ACS, ensure_ascii=False).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"status": "ok", "agent": AGENT_NAME}).encode()
            )


def main():
    port = int(os.getenv("PORT", "8088"))
    server = HTTPServer(("0.0.0.0", port), AIPHandler)
    print(f"[外卖智能体] 启动在 http://0.0.0.0:{port}")
    print(f"[外卖智能体] ACS: http://localhost:{port}/.well-known/acs.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[外卖智能体] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
