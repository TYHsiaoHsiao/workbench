"""批次队列（M14/M15）：入队、状态过滤、顺序执行、失败通知、定时与取消/重排。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import FlowError, default_graph, write_graph_data  # noqa: E402
from flow.queue import (  # noqa: E402
    ALERTS_DEDUPE_MINUTES,
    QUEUE_FILE_NAME,
    alerts_state_path,
    cancel_entry,
    enqueue,
    list_notifications,
    list_queue,
    load_queue,
    move_entry,
    normalize_schedule,
    notify_path,
    queue_path,
    retry_entry,
    run_queue,
    summarize_notifications,
    push_queue_alerts,
)


def make_graph(graph_id: str, project: str) -> dict:
    data = default_graph(project, graph_id=graph_id)
    data["edges"] = [
        {"id": "e-1", "from": {"node": "start", "port": "project"}, "to": {"node": "end", "port": "any"}},
    ]
    return data


class FlowQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("队列测试", base=self.base / "projects")
        self.project = Path(report["path"])

    def _write(self, graph_id: str) -> None:
        write_graph_data(self.project, make_graph(graph_id, self.project.name))

    def _write_broken(self, graph_id: str) -> None:
        data = make_graph(graph_id, self.project.name)
        data["edges"] = []
        write_graph_data(self.project, data)

    def test_enqueue_pending_and_list_filters(self) -> None:
        self._write("flow-a")
        entry = enqueue(self.project, all_graphs=True)
        self.assertEqual("pending", entry["status"])
        self.assertEqual(["flow-a"], entry["graphs"])
        self.assertTrue(queue_path(self.project).is_file())
        self.assertEqual(1, len(list_queue(self.project)))
        self.assertEqual(1, len(list_queue(self.project, status="pending")))
        self.assertEqual(0, len(list_queue(self.project, status="failed")))
        with self.assertRaises(FlowError):
            list_queue(self.project, status="bogus")

    def test_enqueue_dedupes_graph_ids(self) -> None:
        self._write("flow-a")
        self._write("flow-b")
        entry = enqueue(self.project, ["flow-a", "flow-a", "flow-b"])
        self.assertEqual(["flow-a", "flow-b"], entry["graphs"])

    def test_enqueue_rejects_empty_selection(self) -> None:
        with self.assertRaises(FlowError):
            enqueue(self.project, all_graphs=True)
        with self.assertRaises(FlowError):
            enqueue(self.project, [])

    def test_enqueue_parallel_live_rejected(self) -> None:
        self._write("flow-a")
        with self.assertRaises(FlowError):
            enqueue(self.project, all_graphs=True, dry_run=False, parallel=True)
        with self.assertRaises(FlowError):
            enqueue(self.project, all_graphs=True, dry_run=True, parallel=True, fail_fast=True)

    def test_run_queue_in_order_records_batches(self) -> None:
        self._write("flow-a")
        self._write("flow-b")
        first = enqueue(self.project, ["flow-a"])
        second = enqueue(self.project, ["flow-b"])
        result = run_queue(self.project)
        self.assertTrue(result["ok"], result)
        self.assertEqual(2, result["summary"]["total"])
        self.assertEqual(2, result["summary"]["succeeded"])
        self.assertEqual(0, result["summary"]["pending"])
        self.assertEqual([first["queue_id"], second["queue_id"]], [item["queue_id"] for item in result["ran"]])
        for item in result["ran"]:
            self.assertEqual("succeeded", item["status"])
            self.assertTrue(item["batch_id"].startswith("batch-"))
            self.assertIsNone(item["notification"])
        entries = {item["queue_id"]: item for item in list_queue(self.project)}
        self.assertEqual("succeeded", entries[first["queue_id"]]["status"])
        self.assertTrue(entries[first["queue_id"]]["result"]["ok"])
        self.assertEqual(1, entries[first["queue_id"]]["result"]["succeeded"])

    def test_run_queue_failure_notification(self) -> None:
        self._write("flow-ok")
        self._write_broken("flow-bad")
        enqueue(self.project, ["flow-bad"])
        result = run_queue(self.project)
        self.assertFalse(result["ok"], result)
        self.assertEqual(1, result["summary"]["failed"])
        entry = result["ran"][0]
        self.assertEqual("failed", entry["status"])
        self.assertIn("flow-bad", entry["notification"]["failed_graphs"])
        self.assertIn("flow-bad", entry["notification"]["message"])

    def test_run_queue_limit_leaves_rest_pending(self) -> None:
        for graph_id in ("flow-a", "flow-b", "flow-c"):
            self._write(graph_id)
            enqueue(self.project, [graph_id])
        result = run_queue(self.project, limit=1)
        self.assertEqual(1, result["summary"]["total"])
        self.assertEqual(2, result["summary"]["pending"])

    def test_load_queue_missing_returns_empty(self) -> None:
        doc = load_queue(self.project)
        self.assertEqual([], doc["entries"])
        self.assertFalse(queue_path(self.project).exists())
        self.assertEqual(QUEUE_FILE_NAME, queue_path(self.project).name)


class FlowQueueM15Test(unittest.TestCase):
    """M15：计划执行时间、取消与重排。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("队列定时测试", base=self.base / "projects")
        self.project = Path(report["path"])

    def _write(self, graph_id: str) -> None:
        write_graph_data(self.project, make_graph(graph_id, self.project.name))

    def _enqueue(self, graph_id: str, **kwargs) -> dict:
        self._write(graph_id)
        return enqueue(self.project, [graph_id], **kwargs)

    def _order_map(self) -> dict[str, int]:
        doc = load_queue(self.project)
        return {item["queue_id"]: int(item.get("order") or 0) for item in doc["entries"]}

    def test_schedule_future_skipped_and_scheduled_count(self) -> None:
        future = normalize_schedule("2999-01-01T00:00")
        entry = self._enqueue("flow-a", scheduled_at=future)
        self.assertIn("scheduled_at", entry)
        result = run_queue(self.project)
        self.assertEqual(0, result["summary"]["total"])
        self.assertEqual(1, result["summary"]["pending"])
        self.assertEqual(1, result["summary"]["scheduled"])

    def test_schedule_past_runs_immediately(self) -> None:
        past = normalize_schedule("2000-01-01T00:00")
        self._enqueue("flow-a", scheduled_at=past)
        result = run_queue(self.project)
        self.assertEqual(1, result["summary"]["succeeded"])

    def test_cancel_pending_entry_and_not_run(self) -> None:
        entry = self._enqueue("flow-a")
        canceled = cancel_entry(self.project, entry["queue_id"])
        self.assertEqual("canceled", canceled["status"])
        self.assertIn("已取消", canceled["notification"]["message"])
        self.assertEqual(1, len(list_queue(self.project, status="canceled")))
        result = run_queue(self.project)
        self.assertEqual(0, result["summary"]["total"])
        self.assertEqual(0, result["summary"]["pending"])
        self.assertEqual(1, result["summary"]["canceled"])

    def test_cancel_non_pending_rejected(self) -> None:
        entry = self._enqueue("flow-a")
        run_queue(self.project)
        with self.assertRaises(FlowError):
            cancel_entry(self.project, entry["queue_id"])
        with self.assertRaises(FlowError):
            cancel_entry(self.project, "q-00000000-000000-abcdef")

    def test_move_before_reorders_execution(self) -> None:
        first = self._enqueue("flow-a")
        second = self._enqueue("flow-b")
        third = self._enqueue("flow-c")
        moved = move_entry(self.project, third["queue_id"], before=first["queue_id"])
        self.assertEqual(0, moved["order"])
        orders = self._order_map()
        self.assertEqual(0, orders[third["queue_id"]])
        self.assertEqual(1, orders[first["queue_id"]])
        self.assertEqual(2, orders[second["queue_id"]])
        result = run_queue(self.project)
        self.assertEqual(
            [third["queue_id"], first["queue_id"], second["queue_id"]],
            [item["queue_id"] for item in result["ran"]],
        )

    def test_move_after_and_index(self) -> None:
        first = self._enqueue("flow-a")
        second = self._enqueue("flow-b")
        third = self._enqueue("flow-c")
        move_entry(self.project, first["queue_id"], after=second["queue_id"])
        self.assertEqual(1, self._order_map()[first["queue_id"]])
        move_entry(self.project, third["queue_id"], index=0)
        orders = self._order_map()
        self.assertEqual(0, orders[third["queue_id"]])
        self.assertEqual(1, orders[second["queue_id"]])
        self.assertEqual(2, orders[first["queue_id"]])
        result = run_queue(self.project)
        self.assertEqual(
            [third["queue_id"], second["queue_id"], first["queue_id"]],
            [item["queue_id"] for item in result["ran"]],
        )

    def test_move_rejects_invalid_target_or_options(self) -> None:
        first = self._enqueue("flow-a")
        second = self._enqueue("flow-b")
        with self.assertRaises(FlowError):
            move_entry(self.project, first["queue_id"])
        with self.assertRaises(FlowError):
            move_entry(self.project, first["queue_id"], index=0, before=second["queue_id"])
        with self.assertRaises(FlowError):
            move_entry(self.project, first["queue_id"], before="q-00000000-000000-abcdef")
        run_queue(self.project)
        with self.assertRaises(FlowError):
            move_entry(self.project, first["queue_id"], index=0)

    def test_normalize_schedule_validation(self) -> None:
        self.assertIsNone(normalize_schedule(None))
        self.assertIsNone(normalize_schedule("  "))
        self.assertTrue(normalize_schedule("2026-11-15T20:00").startswith("2026-11-15T20:00:00"))
        with self.assertRaises(FlowError):
            normalize_schedule("不是时间")
        with self.assertRaises(FlowError):
            enqueue(self.project, ["flow-a"], scheduled_at="不是时间")


class FlowQueueM16Test(unittest.TestCase):
    """M16：失败重试与通知外送（JSONL 日志 + 外部命令）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("队列重试测试", base=self.base / "projects")
        self.project = Path(report["path"])

    def _write(self, graph_id: str) -> None:
        write_graph_data(self.project, make_graph(graph_id, self.project.name))

    def _write_broken(self, graph_id: str) -> None:
        data = make_graph(graph_id, self.project.name)
        data["edges"] = []
        write_graph_data(self.project, data)

    def _fail_once(self, graph_id: str = "flow-bad") -> dict:
        self._write_broken(graph_id)
        entry = enqueue(self.project, [graph_id])
        result = run_queue(self.project)
        self.assertFalse(result["ok"], result)
        return entry

    def test_retry_entry_resets_failed(self) -> None:
        entry = self._fail_once()
        retried = retry_entry(self.project, entry["queue_id"])
        self.assertEqual("pending", retried["status"])
        self.assertEqual(1, retried["attempts"])
        for key in ("batch_id", "result", "notification", "error", "finished_at", "started_at"):
            self.assertNotIn(key, retried)
        self.assertEqual("pending", list_queue(self.project)[0]["status"])

    def test_retry_non_failed_rejected(self) -> None:
        self._write("flow-a")
        entry = enqueue(self.project, ["flow-a"])
        with self.assertRaises(FlowError):
            retry_entry(self.project, entry["queue_id"])
        with self.assertRaises(FlowError):
            retry_entry(self.project, "q-00000000-000000-abcdef")

    def test_run_queue_retry_failed_bounded(self) -> None:
        entry = self._fail_once()
        result = run_queue(self.project, retry_failed=1)
        self.assertEqual([entry["queue_id"]], result["retried"])
        self.assertFalse(result["ok"])
        items = list_queue(self.project)
        self.assertEqual(1, items[0]["attempts"])
        self.assertEqual("failed", items[0]["status"])
        again = run_queue(self.project, retry_failed=1)
        self.assertEqual([], again["retried"])
        self.assertEqual([], again["ran"])

    def test_notifications_log_written_on_failure(self) -> None:
        self._fail_once()
        notes = list_notifications(self.project)
        self.assertEqual(1, len(notes))
        self.assertEqual("failed", notes[0]["status"])
        self.assertIn("flow-bad", notes[0]["failed_graphs"])
        self.assertIn("队列运行失败", notes[0]["message"])
        self.assertTrue(notify_path(self.project).is_file())

    def test_notify_cmd_receives_message(self) -> None:
        script = self.base / "notify.py"
        out = self.base / "notify.out"
        script.write_text(
            "import sys\nopen(sys.argv[1], 'w', encoding='utf-8').write(sys.argv[2])\n",
            encoding="utf-8",
        )
        self._fail_once()
        enqueue(self.project, ["flow-bad"])
        result = run_queue(self.project, notify_cmd=[sys.executable, str(script), str(out)])
        self.assertTrue(result["notified"], result)
        self.assertIn("队列运行失败", out.read_text(encoding="utf-8"))

    def test_notifications_empty_without_failures(self) -> None:
        self._write("flow-ok")
        enqueue(self.project, ["flow-ok"])
        result = run_queue(self.project)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["notified"])
        self.assertEqual([], list_notifications(self.project))
        self.assertFalse(notify_path(self.project).is_file())


if __name__ == "__main__":
    unittest.main()

class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FlowQueueWebhookTest(unittest.TestCase):
    """M24：失败通知 webhook 外送（JSON POST、失败容错）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("队列 webhook", base=self.base / "projects")
        self.project = Path(report["path"])
        broken = make_graph("flow-webhook", self.project.name)
        broken["edges"] = []
        write_graph_data(self.project, broken)

    def test_webhook_posts_failure_json(self) -> None:
        captured: dict = {}

        def fake_urlopen(request, timeout=10):
            captured["url"] = request.full_url
            captured["body"] = request.data
            return _FakeResponse(200)

        enqueue(self.project, all_graphs=True)
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = run_queue(self.project, webhook_url="http://example.test/hook")
        self.assertTrue(result["webhook"]["configured"])
        self.assertTrue(result["webhook"]["ok"])
        self.assertEqual(200, result["webhook"]["status_code"])
        self.assertTrue(result["notified"] is False)
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("queue.run", body["event"])
        self.assertIn("flow-webhook", body["failed_graphs"])
        self.assertIn("队列运行失败", body["message"])
        self.assertTrue(notify_path(self.project).is_file())

    def test_webhook_failure_tolerated(self) -> None:
        enqueue(self.project, all_graphs=True)
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            result = run_queue(self.project, webhook_url="http://example.test/hook")
        self.assertTrue(result["webhook"]["configured"])
        self.assertFalse(result["webhook"]["ok"])
        self.assertIn("boom", result["webhook"]["error"])
        self.assertFalse(result["ok"])

    def test_webhook_not_configured(self) -> None:
        enqueue(self.project, all_graphs=True)
        result = run_queue(self.project)
        self.assertFalse(result["webhook"]["configured"])


class NotificationSummaryTest(unittest.TestCase):
    """M31：失败通知聚合。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        report = create_project("通知聚合", base=self.base / "projects")
        self.project = Path(report["path"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self, records: list[dict]) -> None:
        path = notify_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")

    def test_aggregates_counts_and_top_graphs(self) -> None:
        self._seed(
            [
                {"at": "2026-11-16T09:00:00", "status": "failed", "message": "队列运行失败 2 条",
                 "failed_graphs": ["g1", "g2"]},
                {"at": "2026-11-16T10:00:00", "status": "failed", "message": "队列运行失败 1 条",
                 "failed_graphs": ["g1"]},
            ]
        )
        summary = summarize_notifications(self.project, limit=10)
        self.assertEqual(2, summary["count"])
        self.assertEqual("2026-11-16T10:00:00", summary["latest_at"])
        self.assertEqual("队列运行失败 1 条", summary["last_message"])
        self.assertEqual(
            [{"graph_id": "g1", "count": 2}, {"graph_id": "g2", "count": 1}],
            summary["failed_graphs"],
        )
        self.assertEqual(2, len(summary["records"]))

    def test_empty_when_no_notifications(self) -> None:
        summary = summarize_notifications(self.project)
        self.assertEqual(0, summary["count"])
        self.assertEqual([], summary["failed_graphs"])
        self.assertEqual("", summary["latest_at"])
        state = summary["state"]
        self.assertEqual(ALERTS_DEDUPE_MINUTES, state["dedupe_minutes"])
        self.assertEqual("", state["last_pushed_at"])
        self.assertEqual("", state["silence_until"])
        self.assertFalse(state["suppressed"])

    def test_state_after_successful_push(self) -> None:
        # M36：成功外送后状态文件记录上次外送时间与静默截止，并在静默窗口内标记 suppressed
        self._seed([{"at": "2026-11-16T09:00:00", "status": "failed", "message": "队列运行失败 1 条",
                     "failed_graphs": ["g1"]}])

        class _FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"ok":true}'

        with mock.patch("urllib.request.urlopen", lambda request, timeout=10: _FakeResponse()):
            result = push_queue_alerts(
                self.project, webhook_url="https://example.test/hook", webhook_format="generic", webhook_retries=0
            )
        self.assertTrue(result["ok"])
        state = summarize_notifications(self.project)["state"]
        self.assertTrue(state["last_pushed_at"])
        self.assertTrue(state["silence_until"])
        self.assertTrue(state["suppressed"])


class AlertsDigestTest(unittest.TestCase):
    """M32：告警摘要外送。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        report = create_project("告警摘要", base=self.base / "projects")
        self.project = Path(report["path"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self, records: list[dict]) -> None:
        path = notify_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")

    def test_push_posts_digest(self) -> None:
        self._seed(
            [
                {"at": "2026-11-16T09:00:00", "status": "failed", "message": "队列运行失败 2 条",
                 "failed_graphs": ["g1", "g2"]},
                {"at": "2026-11-16T10:00:00", "status": "failed", "message": "队列运行失败 1 条",
                 "failed_graphs": ["g1"]},
            ]
        )
        captured: dict = {}

        def fake_urlopen(request, timeout=10):
            captured["body"] = request.data
            return _FakeResponse(200)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = push_queue_alerts(self.project, webhook_url="http://example.test/alerts")
        self.assertTrue(result["ok"])
        self.assertEqual(200, result["webhook"]["status_code"])
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("queue.alerts.digest", body["event"])
        self.assertEqual(2, body["count"])
        self.assertEqual(["g1", "g2"], body["failed_graphs"])
        self.assertIn("队列失败告警摘要", body["message"])

    def test_push_tolerates_failure(self) -> None:
        self._seed([{"at": "2026-11-16T09:00:00", "status": "failed", "message": "x", "failed_graphs": ["g1"]}])
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            result = push_queue_alerts(self.project, webhook_url="http://example.test/alerts")
        self.assertFalse(result["ok"])
        self.assertIn("boom", result["webhook"]["error"])
        self.assertEqual(1, result["summary"]["count"])

    def test_push_requires_webhook(self) -> None:
        with self.assertRaises(FlowError):
            push_queue_alerts(self.project, webhook_url="")

    def test_push_dedupe_suppresses_repeat(self) -> None:
        """M34：相同告警在静默窗口内只外送一次；dedupe_minutes=0 可关闭。"""
        self._seed([{"at": "2026-11-16T09:00:00", "status": "failed", "message": "x", "failed_graphs": ["g1"]}])
        calls = {"n": 0}

        def fake_urlopen(request, timeout=10):
            calls["n"] += 1
            return _FakeResponse(200)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            first = push_queue_alerts(self.project, webhook_url="http://example.test/a", dedupe_minutes=30)
            second = push_queue_alerts(self.project, webhook_url="http://example.test/a", dedupe_minutes=30)
        self.assertFalse(first.get("suppressed"))
        self.assertTrue(second.get("suppressed"))
        self.assertTrue(second["webhook"]["skipped"])
        self.assertEqual(1, calls["n"])
        self.assertTrue(alerts_state_path(self.project).is_file())
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            third = push_queue_alerts(self.project, webhook_url="http://example.test/a", dedupe_minutes=0)
        self.assertFalse(third.get("suppressed"))
        self.assertEqual(2, calls["n"])

    def test_push_dedupe_different_failed_set_sends(self) -> None:
        self._seed([{"at": "2026-11-16T09:00:00", "status": "failed", "message": "x", "failed_graphs": ["g1"]}])
        calls = {"n": 0}

        def fake_urlopen(request, timeout=10):
            calls["n"] += 1
            return _FakeResponse(200)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            push_queue_alerts(self.project, webhook_url="http://example.test/a")
            self._seed(
                [
                    {"at": "2026-11-16T09:00:00", "status": "failed", "message": "x", "failed_graphs": ["g1"]},
                    {"at": "2026-11-16T10:00:00", "status": "failed", "message": "y", "failed_graphs": ["g2"]},
                ]
            )
            changed = push_queue_alerts(self.project, webhook_url="http://example.test/a")
        self.assertFalse(changed.get("suppressed"))
        self.assertEqual(2, calls["n"])
