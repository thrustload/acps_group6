"""ACPs Challenge Server — 严格对齐官方 ACPs-CA-Challenge 源码"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import sys
import json

_store = {}


class ChallengeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """CA Client 存储 challenge"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        path = self.path.strip("/")
        _store[path] = body
        print(f"[POST] /{path}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Challenge set successfully")

    def do_GET(self):
        path = self.path.strip("/")
        print(f"[GET] /{path}")

        # Challenge 验证：/{aic}/{token}（先匹配，避免被通配拦截）
        value = _store.get(path)
        if value:
            print(f"[验证] /{path}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(value.encode())
            return

        # /status — 官方 ACPs-CA-Challenge 源码格式
        if path == "status":
            self._reply_json(200, {
                "server": "Agent HTTP-01 Challenge Server",
                "status": "running",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "host": "0.0.0.0",
                "port": 8765,
                "api_base_path": "/acps-atr-v2",
                "challenge_dir": ".",
                "challenges_count": len(_store),
            })
            return

        # /health — 官方格式
        if path == "health":
            self._reply_json(200, {"status": "OK"})
            return

        # 其余路径 404
        self._reply_json(404, {"detail": "Not Found"})

    def _reply_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, format, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = HTTPServer(("0.0.0.0", port), ChallengeHandler)
    print(f"[Challenge Server] 运行在 http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Challenge Server] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
