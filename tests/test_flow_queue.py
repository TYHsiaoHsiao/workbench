"""批次队列（M14）：入队、状态过滤、顺序执行与失败通知。"""
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
    enqueue,
    list_queue,
    load_queue,
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


if __name__ == "__main__":
    unittest.main()
