"""批次队列（M14/M15）：入队、状态过滤、顺序执行、失败通知、定时与取消/重排。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import FlowError, default_graph, write_graph_data  # noqa: E402
from flow.queue import (  # noqa: E402
    QUEUE_FILE_NAME,
    cancel_entry,
    enqueue,
    list_queue,
    load_queue,
    move_entry,
    normalize_schedule,
    queue_path,
    run_queue,
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


if __name__ == "__main__":
    unittest.main()
