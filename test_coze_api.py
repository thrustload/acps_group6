"""Coze API 调试脚本 v2"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
import time

BOT_ID = sys.argv[1] if len(sys.argv) > 1 else "7641605520465379391"
TOKEN = sys.argv[2] if len(sys.argv) > 2 else "pat_C7b05coaD1kwuXD2LHhVCw2ooNwVP0dSTXHDjRFMdcp6II2J3Xnkid6tj6zbr45j"
MESSAGE = sys.argv[3] if len(sys.argv) > 3 else "今天天气怎么样"

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

print(f"=== Coze API 调试 v2 ===")
print(f"Bot: {BOT_ID} | Msg: {MESSAGE}")
print()

# 1. 发起对话
print("--- Step 1: 发起对话 ---")
resp = requests.post("https://api.coze.cn/v3/chat", json={
    "bot_id": BOT_ID,
    "user_id": "debug_user",
    "stream": False,
    "auto_save_history": True,
    "additional_messages": [{"role": "user", "content": MESSAGE, "content_type": "text"}],
}, headers=HEADERS, timeout=30)

data = resp.json()
print(f"Status: {resp.status_code}, code={data.get('code')}")
if data.get("code") != 0:
    print(f"❌ {data.get('msg')}")
    sys.exit(1)

cid = data["data"]["conversation_id"]
chat_id = data["data"]["id"]
status = data["data"]["status"]
print(f"Chat status: {status}")
print(f"conversation_id: {cid}")
print(f"chat_id: {chat_id}")
print()

# 2. 等几秒后查看 chat 状态
print("--- Step 2: 查看 chat 状态 ---")
time.sleep(3)
r = requests.get(f"https://api.coze.cn/v3/chat/retrieve?conversation_id={cid}&chat_id={chat_id}", headers=HEADERS, timeout=15)
print(f"retrieve: {r.json()}")
print()

# 3. 轮询消息（尝试不同参数）
print("--- Step 3: 轮询消息 ---")
for attempt in range(40):
    time.sleep(1)

    # 尝试不带 query params，只用 conversation_id
    r = requests.get(
        f"https://api.coze.cn/v3/chat/message/list?conversation_id={cid}&chat_id={chat_id}&order=desc",
        headers=HEADERS, timeout=15,
    )
    msgs_data = r.json()
    code = msgs_data.get("code", -1)
    msgs = msgs_data.get("data", [])

    # 也试下 detail 字段
    detail = msgs_data.get("detail", {})

    if msgs:
        print(f"[{attempt+1}] code={code}, msgs={len(msgs)}")
        for m in msgs:
            mtype = m.get("type", "?")
            mrole = m.get("role", "?")
            content = m.get("content", "")[:200]
            print(f"  [{mtype}] {mrole}: {content.encode('utf-8', errors='replace').decode('utf-8', errors='replace')}")
            if mtype == "answer" and mrole == "assistant":
                print(f"\n✅ 回复: {content}")
                sys.exit(0)
    else:
        print(f"[{attempt+1}] code={code}, msgs=0, detail={detail}")

print("\n--- Step 4: 最终 chat/retrieve ---")
r = requests.get(f"https://api.coze.cn/v3/chat/retrieve?conversation_id={cid}&chat_id={chat_id}", headers=HEADERS, timeout=15)
print(r.json())
print()

# 4. 可能是 bot 没发布？查 bot 信息
print("--- Step 5: 查看 bot 信息 ---")
r = requests.get(f"https://api.coze.cn/v1/bot/get_online_info?bot_id={BOT_ID}", headers=HEADERS, timeout=15)
print(f"v1 get_online_info: {r.json()}")
