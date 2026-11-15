"""M6：两次运行 diff 对比。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from flow import compare_runs, format_compare_text  # noqa: E402


def step(node_id: str, status: str, start: str, end: str) -> dict:
    return {
        "node_id": node_id,
        "status": status,
        "started_at": start,
        "ended_at": end,
    }


def make_run(run_id: str, steps: list[dict]) -> dict:
    return {
        "contract_version": "0.1",
        "run_id": run_id,
        "graph_id": "flow-test",
        "project": "对比测试",
        "status": "succeeded",
        "mode": "full",
        "dry_run": True,
        "started_at": "2026-11-15T10:00:00+08:00",
        "finished_at": "2026-11-15T10:00:02+08:00",
        "steps": steps,
    }


class FlowCompareTest(unittest.TestCase):
    def _base(self) -> dict:
        return make_run(
            "run-base",
            [
                step("n1", "succeeded", "2026-11-15T10:00:00+08:00", "2026-11-15T10:00:00.100+08:00"),
                step("n2", "failed", "2026-11-15T10:00:00.100+08:00", "2026-11-15T10:00:00.300+08:00"),
                step("n3", "succeeded", "2026-11-15T10:00:00.300+08:00", "2026-11-15T10:00:00.500+08:00"),
            ],
        )

    def _target(self) -> dict:
        return make_run(
            "run-target",
            [
                step("n1", "succeeded", "2026-11-15T11:00:00+08:00", "2026-11-15T11:00:00.300+08:00"),
                step("n2", "succeeded", "2026-11-15T11:00:00.300+08:00", "2026-11-15T11:00:00.400+08:00"),
                step("n4", "succeeded", "2026-11-15T11:00:00.400+08:00", "2026-11-15T11:00:00.900+08:00"),
            ],
        )

    def test_changes_and_summary(self) -> None:
        diff = compare_runs(self._base(), self._target())
        changes = {item["node_id"]: item["change"] for item in diff["node_changes"]}
        self.assertEqual("slower", changes["n1"])
        self.assertEqual("status_changed", changes["n2"])
        self.assertEqual("removed", changes["n3"])
        self.assertEqual("added", changes["n4"])
        summary = diff["summary"]
        self.assertEqual(3, summary["base_steps"])
        self.assertEqual(3, summary["target_steps"])
        self.assertEqual(500, summary["base_total_ms"])
        self.assertEqual(900, summary["target_total_ms"])
        self.assertEqual(400, summary["total_delta_ms"])
        self.assertGreaterEqual(summary["regressed"], 2)
        self.assertGreaterEqual(summary["improved"], 0)

    def test_same_runs_are_stable(self) -> None:
        base = self._base()
        diff = compare_runs(base, base)
        self.assertEqual([], [item for item in diff["node_changes"] if item["change"] != "same"])
        self.assertEqual(0, diff["summary"]["regressed"])
        self.assertEqual(0, diff["summary"]["improved"])

    def test_format_text(self) -> None:
        text = format_compare_text(compare_runs(self._base(), self._target()))
        self.assertIn("运行对比", text)
        self.assertIn("n1", text)
        self.assertIn("总耗时", text)


if __name__ == "__main__":
    unittest.main()
