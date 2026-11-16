"""批次失败 webhook 外送（M28）：配置时 POST JSON、失败容错、未配置 no-op。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import default_graph, read_batch, run_batch, write_graph_data  # noqa: E402


def _graph(graph_id: str, project: str) -> dict:
    data = default_graph(project, graph_id=graph_id)
    data["edges"] = [
        {
            "id": "e-1",
            "from": {"node": "start", "port": "project"},
            "to": {"node": "end", "port": "any"},
        }
    ]
    return data


def _broken_graph(graph_id: str, project: str) -> dict:
    data = _graph(graph_id, project)
    data["edges"] = []
    return data


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class BatchWebhookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        report = create_project("批次通知测试", base=self.base / "projects")
        self.project = Path(report["path"])
        write_graph_data(self.project, _broken_graph("flow-webhook-bad", str(self.project)))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_failed_batch_posts_webhook(self) -> None:
        requests: list = []

        def fake_urlopen(request, timeout=None):
            requests.append((request, timeout))
            return _FakeResponse(200)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            result = run_batch(
                self.project,
                all_graphs=True,
                dry_run=True,
                webhook_url="https://hooks.example.test/batch",
            )
        self.assertFalse(result["ok"])
        webhook = result["webhook"]
        self.assertTrue(webhook["configured"])
        self.assertTrue(webhook["ok"])
        self.assertEqual(webhook["status_code"], 200)
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 10)
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["event"], "batch.run")
        self.assertEqual(payload["project"], self.project.name)
        self.assertIn("flow-webhook-bad", payload["failed_graphs"])
        self.assertIn("批次", payload["message"])

    def test_webhook_failure_does_not_break_batch(self) -> None:
        def fake_urlopen(request, timeout=None):
            raise OSError("boom")

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            result = run_batch(
                self.project,
                all_graphs=True,
                dry_run=True,
                webhook_url="https://hooks.example.test/batch",
            )
        self.assertEqual(result["batch"]["status"], "failed")
        webhook = result["webhook"]
        self.assertTrue(webhook["configured"])
        self.assertFalse(webhook["ok"])
        self.assertIn("boom", webhook["error"])
        self.assertTrue(read_batch(self.project, result["batch"]["batch_id"])["batch_id"])

    def test_no_webhook_configured_is_noop(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("不应调用 urlopen")):
            result = run_batch(self.project, all_graphs=True, dry_run=True)
        self.assertFalse(result["webhook"]["configured"])
        self.assertFalse(result["webhook"]["ok"])


if __name__ == "__main__":
    unittest.main()
