"""Leader Bridge — Coze 云端插件 ↔ 内网 Partner 的桥接服务"""
import json
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# AIC 映射
LEADER_AIC = "1.2.156.3088.0001.00001.A53M96.AXQY6W.1.1AZ7"
PARTNER_AIC = {
    "北邮校园外卖小助手": "1.2.156.3088.0001.00001.4UBXND.RABBX9.1.0ITQ",
    "快递小助手": "1.2.156.3088.0001.00001.ZDEPKT.696GQR.1.05FY",
    "天气穿搭管家": "1.2.156.3088.0001.00001.7DRAS3.51UTCT.1.12PU",
    "约会规划师": "1.2.156.3088.0001.00001.REPPEE.8FA2BW.1.13SF",
}

# Partner 内网地址
PARTNERS = {
    "北邮校园外卖小助手": "http://127.0.0.1:8088",
    "快递小助手": "http://127.0.0.1:8089",
    "天气穿搭管家": "http://127.0.0.1:8090",
    "约会规划师": "http://127.0.0.1:8091",
}

DISCOVERY_URL = "http://117.74.66.90:8005/acps-dsp-v2"
FOOTPRINT_URL = "http://117.74.66.90:8006/notify"


class BridgeHandler(BaseHTTPRequestHandler):
    def _reply(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        path = self.path.strip("/")

        if path == "search":
            # 查询发现服务器
            try:
                resp = requests.post(
                    f"{DISCOVERY_URL}/discovery/search",
                    json={
                        "type": "exploratory",
                        "query": body.get("query", ""),
                        "limit": 5,
                    },
                    timeout=10,
                )
                self._reply(200, resp.json())
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path == "call":
            # 转发到指定 Partner
            agent_name = body.get("agent", "")
            message = body.get("message", "")
            session_id = body.get("session_id", "")

            agent_url = PARTNERS.get(agent_name)
            if not agent_url:
                self._reply(404, {"error": f"未知智能体: {agent_name}"})
                return

            try:
                resp = requests.post(
                    agent_url,
                    json={
                        "message": message,
                        "session_id": session_id,
                        "caller_name": "北邮个人助手",
                        "caller_aic": body.get("caller_aic", ""),
                    },
                    timeout=30,
                )
                self._reply(200, resp.json())
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path == "footprint":
            # 上报态势大屏（自动补全 AIC）
            try:
                dst_name = body.get("dst_name", "")
                requests.post(
                    FOOTPRINT_URL,
                    json={
                        "AgentName_src": body.get("src_name", "北邮个人助手"),
                        "src_AIC": body.get("src_aic") or LEADER_AIC,
                        "AgentName_dist": dst_name,
                        "dest_AIC": body.get("dst_aic") or PARTNER_AIC.get(dst_name, ""),
                    },
                    timeout=5,
                )
                self._reply(200, {"status": "ok"})
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path == "status":
            self._reply(200, {"status": "running"})

        else:
            self._reply(404, {"error": "not found"})

    def do_GET(self):
        self._reply(200, {"status": "running", "partners": list(PARTNERS.keys())})

    def log_message(self, format, *args):
        pass


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    server = HTTPServer(("0.0.0.0", port), BridgeHandler)
    print(f"[Leader Bridge] http://0.0.0.0:{port}")
    print(f"  POST /search    - 查询发现服务器")
    print(f"  POST /call      - 调 Partner")
    print(f"  POST /footprint - 上报大屏")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Leader Bridge] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
