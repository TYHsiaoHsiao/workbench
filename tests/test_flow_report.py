"""M33：批次趋势报表（Markdown/CSV）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import default_graph, write_graph_data  # noqa: E402
from flow.batch import run_batch  # noqa: E402
from flow.report import REPORT_FORMATS, batch_report  # noqa: E402


def make_graph(graph_id: str) -> dict:
    data = default_graph(graph_id)
    data["graph_id"] = graph_id
    data["name"] = graph_id
    data["edges"].append(
        {"id": "e-1", "from": {"node": "start", "port": "project"}, "to": {"node": "end", "port": "any"}}
    )
    return data


class BatchReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        report = create_project("报表测试", base=base / "projects")
        self.project = Path(report["path"])
        write_graph_data(self.project, make_graph("flow-a"))
        write_graph_data(self.project, make_graph("flow-b"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_batches(self) -> None:
        run_batch(self.project, ["flow-a", "flow-b"], dry_run=True)
        run_batch(self.project, ["flow-a"], dry_run=True)

    def test_markdown_report(self) -> None:
        self._make_batches()
        report = batch_report(self.project, limit=10, fmt="md")
        self.assertTrue(report["ok"])
        self.assertEqual("md", report["format"])
        self.assertIn("批次趋势报表", report["text"])
        self.assertIn("| 批次 | 开始时间 | 状态 | 图数 | 成功 | 失败 | 耗时(ms) |", report["text"])
        self.assertIn("成功率 100.0%", report["text"])
        self.assertEqual(2, report["summary"]["batches"])
        self.assertEqual(3, report["summary"]["total"])
        self.assertEqual("100.0%", report["summary"]["success_rate"])

    def test_csv_report(self) -> None:
        self._make_batches()
        report = batch_report(self.project, limit=10, fmt="csv")
        lines = report["text"].strip().splitlines()
        self.assertEqual(3, len(lines))
        self.assertTrue(lines[0].startswith("batch_id,"))
        self.assertIn("started_at", lines[0])
        self.assertIn("auto_retry", lines[0])
        self.assertEqual(2, report["summary"]["batches"])

    def test_empty_project(self) -> None:
        report = batch_report(self.project, limit=10, fmt="md")
        self.assertEqual(0, report["summary"]["batches"])
        self.assertEqual(0, report["summary"]["total"])
        self.assertIn("0.0%", report["text"])

    def test_unknown_format(self) -> None:
        with self.assertRaises(ValueError):
            batch_report(self.project, fmt="xlsx")
        self.assertEqual(["md", "csv"], list(REPORT_FORMATS))


if __name__ == "__main__":
    unittest.main()
