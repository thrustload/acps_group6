import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class StaticFileResolutionTests(unittest.TestCase):
    def test_resolve_static_path_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            web_dir = root / "web"
            web_dir.mkdir()
            (web_dir / "index.html").write_text("ok", encoding="utf-8")
            (root / "web_app.py").write_text("secret", encoding="utf-8")

            with mock.patch.object(web_app, "WEB_DIR", web_dir):
                self.assertEqual(
                    web_app.resolve_static_path("/index.html"),
                    (web_dir / "index.html").resolve(),
                )
                self.assertIsNone(web_app.resolve_static_path("/../web_app.py"))


if __name__ == "__main__":
    unittest.main()
