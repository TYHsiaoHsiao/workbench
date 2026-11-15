"""批量运行引擎（M12）：批次记录、自动重试、失败即停与会话登记。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import (  # noqa: E402
    FlowError,
    batch_path,
    batches_dir,
    default_graph,
    list_batches,
    list_runs,
    read_batch,
    recover_batch,
    run_batch,
    write_graph_data,
)


def make_node(node_id: str, node_type: str, project: str, x: int = 0) -> dict:
    params: dict = {}
    if node_type == "start":
        params = {"project": project, "entry": "A"}
    elif node_type == "confirm":
        params = {"prompt": "确认继续"}
    return {
        "id": node_id,
        "type": node_type,
        "label": node_type,
        "position": {"x": x, "y": 140},
        "params": params,
    }


def edge(edge_id: str, from_node: str, from_port: str, to_node: str, to_port: str) -> dict:
    return {
        "id": edge_id,
        "from": {"node": from_node, "port": from_port},
        "to": {"node": to_node, "port": to_port},
    }


def make_graph(graph_id: str, project: str) -> dict:
    data = default_graph(project, graph_id=graph_id)
    data["edges"] = [
        edge("e-1", "start", "project", "end", "any"),
    ]
    return data


class FlowBatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("批量测试", base=self.base / "projects")
        self.project = Path(report["path"])

    def _write(self, graph_id: str) -> None:
        write_graph_data(self.project, make_graph(graph_id, self.project.name))

    def _write_broken(self, graph_id: str) -> None:
        data = make_graph(graph_id, self.project.name)
        data["edges"] = []
        write_graph_data(self.project, data)

    def test_batch_dry_run_saves_record(self) -> None:
        self._write("flow-test")
        result = run_batch(self.project, dry_run=True)
        self.assertTrue(result["ok"], result)
        batch = result["batch"]
        self.assertEqual("succeeded", batch["status"])
        self.assertEqual(1, batch["summary"]["total"])
        self.assertEqual(1, batch["summary"]["succeeded"])
        self.assertEqual(1, batch["summary"]["attempts"])
        self.assertTrue(batch_path(self.project, batch["batch_id"]).is_file())
        self.assertEqual(batch["batch_id"], read_batch(self.project, batch["batch_id"])["batch_id"])
        entries = list_batches(self.project)
        self.assertEqual(batch["batch_id"], entries[0]["batch_id"])
        self.assertEqual(1, entries[0]["total"])

    def test_batch_auto_retry_failed_graph(self) -> None:
        self._write("flow-test")
        self._write_broken("flow-bad")
        result = run_batch(self.project, ["flow-bad", "flow-test"], dry_run=True, auto_retry=1)
        self.assertFalse(result["ok"])
        batch = result["batch"]
        by_id = {item["graph_id"]: item for item in batch["graphs"]}
        self.assertEqual("error", by_id["flow-bad"]["status"])
        self.assertFalse(by_id["flow-bad"]["ok"])
        self.assertEqual(2, len(by_id["flow-bad"]["attempts"]))
        self.assertEqual(1, len(by_id["flow-test"]["attempts"]))
        self.assertEqual(1, batch["summary"]["failed"])
        self.assertEqual(1, batch["summary"]["succeeded"])
        self.assertEqual(3, batch["summary"]["attempts"])
        saved = read_batch(self.project, batch["batch_id"])
        self.assertEqual("failed", saved["status"])
        self.assertEqual(2, len(saved["graphs"][0]["attempts"]))
        # 校验失败的图不会落运行记录，仅有成功图产生 1 条 run
        self.assertEqual(1, len(list_runs(self.project, limit=10)))

    def test_batch_fail_fast_skips_remaining(self) -> None:
        self._write("flow-test")
        self._write_broken("flow-bad")
        result = run_batch(self.project, ["flow-bad", "flow-test"], dry_run=True, fail_fast=True)
        batch = result["batch"]
        self.assertEqual(1, len(batch["graphs"]))
        self.assertEqual(1, batch["summary"]["skipped"])
        self.assertEqual(1, batch["summary"]["total"])

    def test_batch_limit(self) -> None:
        for graph_id in ("flow-a", "flow-b", "flow-c"):
            self._write(graph_id)
        result = run_batch(self.project, all_graphs=True, dry_run=True, limit=2)
        self.assertEqual(2, result["batch"]["summary"]["total"])

    def test_batch_awaiting_confirm_registers_session(self) -> None:
        data = {
            "contract_version": "0.1",
            "graph_id": "flow-confirm",
            "name": "确认流程",
            "project": self.project.name,
            "created_at": "2026-11-15T00:00:00+08:00",
            "updated_at": "2026-11-15T00:00:00+08:00",
            "nodes": [
                make_node("start", "start", self.project.name),
                make_node("confirm", "confirm", self.project.name, x=300),
                make_node("end", "end", self.project.name, x=600),
            ],
            "edges": [
                edge("e-1", "start", "project", "confirm", "text"),
                edge("e-2", "confirm", "confirmed", "end", "any"),
            ],
            "settings": {"auto_advance": True, "allow_skip_stages": False, "dry_run_first": True},
        }
        write_graph_data(self.project, data)
        sessions: dict = {}
        result = run_batch(self.project, ["flow-confirm"], dry_run=False, auto_confirm=False, sessions=sessions)
        batch = result["batch"]
        entry = batch["graphs"][0]
        self.assertEqual("awaiting_confirm", entry["status"])
        self.assertTrue(entry["ok"])
        self.assertEqual(1, len(sessions))
        self.assertIn(entry["run_id"], sessions)

    def test_batch_parallel_dry_run(self) -> None:
        self._write("flow-a")
        self._write("flow-b")
        result = run_batch(self.project, all_graphs=True, dry_run=True, parallel=True, workers=2)
        batch = result["batch"]
        self.assertTrue(batch["parallel"])
        self.assertEqual(2, batch["workers"])
        self.assertEqual("succeeded", batch["status"])
        self.assertEqual(2, batch["summary"]["succeeded"])
        entries = list_batches(self.project)
        self.assertTrue(entries[0]["parallel"])
        self.assertEqual(2, entries[0]["workers"])

    def test_batch_parallel_rejects_live_and_fail_fast(self) -> None:
        self._write("flow-a")
        with self.assertRaises(FlowError):
            run_batch(self.project, all_graphs=True, dry_run=False, parallel=True)
        with self.assertRaises(FlowError):
            run_batch(self.project, all_graphs=True, dry_run=True, parallel=True, fail_fast=True)

    def test_recover_batch_merges_attempts(self) -> None:
        self._write("flow-test")
        self._write_broken("flow-bad")
        result = run_batch(self.project, ["flow-bad", "flow-test"], dry_run=True)
        batch = result["batch"]
        self.assertFalse(result["ok"], result)
        self._write("flow-bad")  # 修复后再恢复
        recovered = recover_batch(self.project, batch["batch_id"])
        self.assertTrue(recovered["ok"], recovered)
        self.assertEqual(1, recovered["recovered"])
        saved = read_batch(self.project, batch["batch_id"])
        self.assertEqual("succeeded", saved["status"])
        by_id = {item["graph_id"]: item for item in saved["graphs"]}
        self.assertTrue(by_id["flow-bad"]["ok"])
        self.assertEqual(2, len(by_id["flow-bad"]["attempts"]))
        self.assertEqual([1, 2], [attempt["attempt"] for attempt in by_id["flow-bad"]["attempts"]])
        self.assertEqual(0, saved["summary"]["failed"])
        self.assertEqual(3, saved["summary"]["attempts"])

    def test_recover_batch_without_failures(self) -> None:
        self._write("flow-test")
        batch = run_batch(self.project, dry_run=True)["batch"]
        recovered = recover_batch(self.project, batch["batch_id"])
        self.assertTrue(recovered["ok"])
        self.assertEqual(0, recovered["recovered"])

    def test_read_batch_rejects_bad_id(self) -> None:
        self._write("flow-test")
        run_batch(self.project, dry_run=True)
        with self.assertRaises(FlowError):
            read_batch(self.project, "../escape")
        with self.assertRaises(FlowError):
            read_batch(self.project, "batch-does-not-exist")
        self.assertTrue(batches_dir(self.project).is_dir())


if __name__ == "__main__":
    unittest.main()
