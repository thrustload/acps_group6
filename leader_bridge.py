"""Leader Bridge — Coze 插件 ↔ ADP 发现 + 动态路由 Partner"""
import json
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

LEADER_AIC = "1.2.156.3088.0001.00001.A53M96.AXQY6W.1.1AZ7"
DISCOVERY_URL = "http://117.74.66.90:8005/acps-adp-v2/discover"
FOOTPRINT_URL = "http://117.74.66.90:8006/notify"

# 本地默认兜底地址（ADP 返回了就用 ADP 的）
PARTNERS = {
    "北邮校园外卖小助手": "http://127.0.0.1:8088",
    "快递小助手": "http://127.0.0.1:8089",
    "天气穿搭管家": "http://127.0.0.1:8090",
    "约会规划师": "http://127.0.0.1:8091",
}

# ADP 搜索结果缓存: {agent_name: {"aic": ..., "endpoint": ..., "acs": {...}}}
_agent_cache = {}


class BridgeHandler(BaseHTTPRequestHandler):
    def _reply(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _cache_from_acs_map(self, acs_map):
        """从 ADP 返回的 acsMap 提取名称→地址的映射"""
        for aic, acs in acs_map.items():
            name = acs.get("name", "")
            endpoints = acs.get("endPoints", [])
            url = endpoints[0]["url"] if endpoints else ""
            _agent_cache[name] = {
                "aic": aic,
                "endpoint": url,
                "acs": acs,
            }

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        path = self.path.strip("/")

        if path == "search":
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
            # 公网直连入口: POST /partner/北邮校园外卖小助手
            agent_name = path.replace("partner/", "").strip()
            agent_url = PARTNERS.get(agent_name)
            if not agent_url:
                self._reply(404, {"error": f"未知智能体: {agent_name}"})
                return
            try:
                resp = requests.post(agent_url, json=body, timeout=30)
                print(f"[公网直连] {agent_name} → {agent_url}")
                self._reply(200, resp.json())
            except Exception as e:
                self._reply(500, {"error": str(e)})

        elif path == "call":
            agent_name = body.get("agent", "")
            message = body.get("message", "")
            session_id = body.get("session_id", "")

            # 优先从 ADP 缓存取地址，其次用本地兜底
            cached = _agent_cache.get(agent_name, {})
            agent_url = cached.get("endpoint") or PARTNERS.get(agent_name)
            if not agent_url:
                self._reply(404, {"error": f"未知智能体: {agent_name}", "cached": list(_agent_cache.keys())})
                return

            try:
                caller_aic = body.get("caller_aic") or LEADER_AIC
                resp = requests.post(
                    agent_url,
                    json={
                        "message": message,
                        "session_id": session_id,
                        "caller_name": "北邮个人助手",
                        "caller_aic": caller_aic,
                    },
                    timeout=30,
                )
                print(f"[调用] {agent_name} → {agent_url}")
                self._reply(200, resp.json())
            except Exception as e:
                self._reply(500, {"error": str(e)})

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
                "fallback_agents": list(PARTNERS.keys()),
            })

        else:
            self._reply(404, {"error": "not found"})

    def do_GET(self):
        self._reply(200, {
            "status": "running",
            "cached_agents": list(_agent_cache.keys()),
            "fallback_agents": list(PARTNERS.keys()),
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
