"""Coze 智能体 API 适配层 (v3 异步版)"""
import requests
import time


class CozeAgent:
    def __init__(self, bot_id: str, token: str):
        self.bot_id = bot_id
        self.token = token

    def chat(self, user_id: str, message: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        # 1. 发起对话
        body = {
            "bot_id": self.bot_id,
            "user_id": user_id,
            "stream": False,
            "auto_save_history": True,
            "additional_messages": [
                {"role": "user", "content": message, "content_type": "text"}
            ],
        }
        resp = requests.post("https://api.coze.cn/v3/chat", json=body, headers=headers, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            return f"[Coze错误] {data.get('msg', '未知错误')}"
        cid = data["data"]["conversation_id"]
        chat_id = data["data"]["id"]

        # 2. 轮询获取回复
        for _ in range(15):
            time.sleep(2)
            r = requests.get(
                f"https://api.coze.cn/v3/chat/message/list?conversation_id={cid}&chat_id={chat_id}",
                headers=headers,
            )
            msgs = r.json().get("data", [])
            for m in msgs:
                if m.get("type") == "answer" and m.get("role") == "assistant":
                    return m["content"]
        return "[Coze] 未获取到回复"
