"""M33：通知外送增强（重试/退避、飞书消息格式）。零依赖，mock urlopen。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from flow.notify import WEBHOOK_FORMATS, build_webhook_body, notify_webhook  # noqa: E402


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class WebhookBodyTest(unittest.TestCase):
    def test_generic_passthrough(self) -> None:
        payload = {"event": "queue.run", "message": "失败", "failed_graphs": ["g1"]}
        self.assertEqual(payload, build_webhook_body(payload, "generic"))

    def test_feishu_text_body(self) -> None:
        payload = {"event": "queue.run", "message": "队列运行失败 1 条", "failed_graphs": ["g1", "g2"]}
        body = build_webhook_body(payload, "feishu")
        self.assertEqual("text", body["msg_type"])
        text = body["content"]["text"]
        self.assertIn("AI 影视工作台", text)
        self.assertIn("队列运行失败 1 条", text)
        self.assertIn("g1、g2", text)

    def test_unknown_format_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_webhook_body({"message": "x"}, "slack")
        self.assertIn("generic", WEBHOOK_FORMATS)
        self.assertIn("feishu", WEBHOOK_FORMATS)


class WebhookRetryTest(unittest.TestCase):
    def test_retry_succeeds_on_second_attempt(self) -> None:
        calls: list[bytes] = []

        def fake_urlopen(request, timeout=10):
            calls.append(request.data)
            if len(calls) == 1:
                raise OSError("temporary")
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = notify_webhook("http://example.test/hook", {"message": "x"}, retries=1, backoff=0)
        self.assertTrue(result["ok"])
        self.assertEqual(2, result["attempts"])
        self.assertEqual(2, len(calls))

    def test_retries_exhausted(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")) as mocked:
            result = notify_webhook("http://example.test/hook", {"message": "x"}, retries=2, backoff=0)
        self.assertFalse(result["ok"])
        self.assertEqual(3, result["attempts"])
        self.assertEqual(3, mocked.call_count)
        self.assertIn("boom", result["error"])

    def test_not_configured_no_attempt(self) -> None:
        with mock.patch("urllib.request.urlopen") as mocked:
            result = notify_webhook(None, {"message": "x"})
        self.assertFalse(result["configured"])
        mocked.assert_not_called()

    def test_feishu_request_body(self) -> None:
        captured: dict = {}

        def fake_urlopen(request, timeout=10):
            captured["body"] = request.data
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = notify_webhook(
                "http://example.test/hook",
                {"event": "batch.run", "message": "批次失败", "failed_graphs": ["g1"]},
                format="feishu",
            )
        self.assertTrue(result["ok"])
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("text", body["msg_type"])
        self.assertIn("批次失败", body["content"]["text"])


if __name__ == "__main__":
    unittest.main()
