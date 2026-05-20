"""约会规划师 ACPs 接入主程序"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ACPs_Footprint import ACPs_Footprint
from coze_client import CozeAgent

# ===== 配置 =====
AGENT_NAME = "约会规划师"
COZE_BOT_ID = os.getenv("DATE_BOT_ID", "7641605520465379391")
COZE_TOKEN = os.getenv("DATE_TOKEN", "cztei_l9Rol4fVm6jR7rTdfaRLp6tu2VfnyNM6Gjc71s8Cc46xme0j4IkiTnrWn3xMSPWfI")
MY_AIC = "1.2.156.3088.0001.00001.REPPEE.8FA2BW.1.13SF"
DISPLAY_SERVER_URL = "http://117.74.66.90:8006/notify"

coze = CozeAgent(bot_id=COZE_BOT_ID, token=COZE_TOKEN)

ACS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acs.json")
with open(ACS_PATH, "r", encoding="utf-8") as f:
    ACS = json.load(f)


def notify_to_dashboard(src_name, src_aic, dst_name, dst_aic):
    ACPs_Footprint.notify(
        url=DISPLAY_SERVER_URL,
        AgentName_src=src_name,
        src_AIC=src_aic,
        AgentName_dist=dst_name,
        dest_AIC=dst_aic,
    )


from http.server import HTTPServer, BaseHTTPRequestHandler


class AIPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body)

        caller_name = data.get("caller_name", "未知")
        caller_aic = data.get("caller_aic", "未知")
        notify_to_dashboard(caller_name, caller_aic, AGENT_NAME, MY_AIC)

        user_message = data.get("message", "")
        user_id = data.get("session_id", "default")
        reply = coze.chat(user_id=user_id, message=user_message)

        result = {"status": "completed", "agent": AGENT_NAME, "aic": MY_AIC, "reply": reply}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())

    def do_GET(self):
        if self.path == "/.well-known/acs.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(ACS, ensure_ascii=False).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "agent": AGENT_NAME}).encode())


def main():
    port = int(os.getenv("PORT", "8091"))
    server = HTTPServer(("0.0.0.0", port), AIPHandler)
    print(f"[{AGENT_NAME}] http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{AGENT_NAME}] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
