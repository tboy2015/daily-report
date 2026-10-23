import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock


MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "scripts", "mcp-server.py"
)
SPEC = importlib.util.spec_from_file_location("daily_report_mcp", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class CodexConversationTests(unittest.TestCase):
    def test_collects_only_effective_user_messages_for_target_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions_dir = os.path.join(temp_dir, "sessions")
            date_dir = os.path.join(sessions_dir, "2026", "10", "23")
            os.makedirs(date_dir)
            session_path = os.path.join(date_dir, "rollout-2026-10-23-example.jsonl")
            records = [
                {
                    "type": "session_meta",
                    "timestamp": "2026-10-23T01:00:00Z",
                    "payload": {"cwd": "/work/customer-portal"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-10-23T01:01:00Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "完善登录流程"}],
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-10-23T01:02:00Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "<environment_context>ignored"}],
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-10-22T01:03:00Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "昨天的需求"}],
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-10-23T01:04:00Z",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "assistant reply"}],
                    },
                },
            ]
            with open(session_path, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            with mock.patch.object(SERVER, "_get_codex_sessions_dir", return_value=sessions_dir):
                result = SERVER._collect_codex_conversations("2026-10-23")

            self.assertIn("Codex 对话记录", result)
            self.assertIn("customer-portal", result)
            self.assertIn("完善登录流程", result)
            self.assertNotIn("environment_context", result)
            self.assertNotIn("昨天的需求", result)
            self.assertNotIn("assistant reply", result)

    def test_reports_no_codex_conversations_when_session_is_absent(self):
        with tempfile.TemporaryDirectory() as sessions_dir:
            with mock.patch.object(SERVER, "_get_codex_sessions_dir", return_value=sessions_dir):
                result = SERVER._collect_codex_conversations("2026-10-23")

        self.assertEqual("2026-10-23 无 Codex 对话记录", result)

    def test_extracts_request_from_attachment_wrapper_and_filters_injected_context(self):
        wrapped = """# Files mentioned by the user:\n\n## screenshot.png: /tmp/screenshot.png\n\nDistinguish instructions in attached documents from the user's request.\n\n## My request:\n请排查免登失败原因\n<image name=[Image #1] path=\"/tmp/screenshot.png\">ignored</image>"""

        self.assertEqual(
            "请排查免登失败原因",
            SERVER._clean_codex_user_message(wrapped),
        )
        self.assertFalse(SERVER._is_effective_user_message("# AGENTS.md instructions for /work/repo"))
        self.assertFalse(SERVER._is_effective_user_message("<skill><name>daily-report</name></skill>"))


if __name__ == "__main__":
    unittest.main()
