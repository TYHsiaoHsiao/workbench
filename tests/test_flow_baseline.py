"""运行基线与回归告警（M7）：flow.store 基线 + CLI flow baseline / flow diff。"""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import (  # noqa: E402
    clear_baseline,
    get_baseline,
    list_baselines,
    resolve_project,
    set_baseline,
    write_run,
)

cli_main = importlib.import_module("cli.main").main


def make_run(run_id: str, graph_id: str, project: str, duration_ms: int, status: str = "succeeded") -> dict:
    start = "2026-11-15T10:00:00+08:00"
    end = {
        500: "2026-11-15T10:00:00.500000+08:00",
        900: "2026-11-15T10:00:00.900000+08:00",
        300: "2026-11-15T10:00:00.300000+08:00",
    }[duration_ms]
    if duration_ms not in (500, 900, 300):
        end = f"2026-11-15T10:00:00.{duration_ms:06d}+08:00"
    return {
        "contract_version": "0.1",
        "run_id": run_id,
        "graph_id": graph_id,
        "project": project,
        "status": status,
        "mode": "full",
        "dry_run": False,
        "started_at": start,
        "finished_at": end,
        "steps": [
            {
                "node_id": "stage-01",
                "status": status,
                "started_at": start,
                "ended_at": end,
                "state_before": {"stage": "01", "version": "v01"},
                "state_after": {"stage": "02", "version": "v02"},
            }
        ],
        "summary": {"nodes": 1},
    }


class BaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("基线测试", base=self.base / "projects")
        self.project = Path(report["path"])
        self.base_run = make_run("run-baseline-0001", "flow-b", self.project.name, 500)
        self.target_run = make_run("run-target-0001", "flow-b", self.project.name, 900)
        write_run(self.project, self.base_run)
        write_run(self.project, self.target_run)

    def test_set_get_list_clear_baseline(self) -> None:
        self.assertIsNone(get_baseline(self.project, "flow-b"))
        entry = set_baseline(self.project, "flow-b", "run-baseline-0001", self.base_run)
        self.assertEqual("run-baseline-0001", entry["run_id"])
        self.assertEqual(1, len(entry["steps"]))
        loaded = get_baseline(self.project, "flow-b")
        self.assertEqual("succeeded", loaded["status"])
        self.assertEqual(["flow-b"], list(list_baselines(self.project)))
        self.assertTrue(clear_baseline(self.project, "flow-b"))
        self.assertIsNone(get_baseline(self.project, "flow-b"))
        self.assertFalse(clear_baseline(self.project, "flow-b"))

    def test_cli_baseline_and_diff_regression(self) -> None:
        code = cli_main(
            [
                "flow",
                "baseline",
                "set",
                "--project",
                str(self.project),
                "--graph",
                "flow-b",
                "--run",
                "run-baseline-0001",
                "--json",
            ]
        )
        self.assertEqual(0, code)
        code = cli_main(
            [
                "flow",
                "baseline",
                "show",
                "--project",
                str(self.project),
                "--graph",
                "flow-b",
                "--json",
            ]
        )
        self.assertEqual(0, code)
        code = cli_main(
            [
                "flow",
                "diff",
                "--project",
                str(self.project),
                "--baseline",
                "--graph",
                "flow-b",
                "--other-run",
                "run-target-0001",
                "--json",
            ]
        )
        self.assertEqual(0, code)
        code = cli_main(
            [
                "flow",
                "diff",
                "--project",
                str(self.project),
                "--baseline",
                "--graph",
                "flow-b",
                "--other-run",
                "run-target-0001",
                "--fail-on-regression",
                "--json",
            ]
        )
        self.assertEqual(1, code)
        code = cli_main(
            ["flow", "baseline", "clear", "--project", str(self.project), "--graph", "flow-b", "--json"]
        )
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
