"""批次趋势报表（Markdown/CSV/HTML）与趋势 SVG 图（M33/M35/M37）。"""
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
from flow import default_graph, write_graph_data  # noqa: E402
from flow.batch import run_batch  # noqa: E402
from flow.graph import FlowError  # noqa: E402
from flow.report import REPORT_FORMATS, batch_report, batch_trend_svg, push_batch_report  # noqa: E402


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

    def test_html_report(self) -> None:
        # M35：自包含 HTML 报表（内联样式、汇总卡片、趋势条、明细表）
        self._make_batches()
        report = batch_report(self.project, limit=10, fmt="html")
        self.assertTrue(report["ok"])
        self.assertEqual("html", report["format"])
        self.assertIn("<!DOCTYPE html>", report["text"])
        self.assertIn("<style>", report["text"])
        self.assertIn("批次趋势报表", report["text"])
        self.assertIn("成功率", report["text"])
        self.assertIn('class="bar-fill', report["text"])
        self.assertIn("<table>", report["text"])
        self.assertNotIn("http://", report["text"])
        self.assertNotIn("https://", report["text"])
        # HTML 转义：项目名不直接拼接标签
        self.assertIn("报表测试", report["text"])

    def test_unknown_format(self) -> None:
        with self.assertRaises(ValueError):
            batch_report(self.project, fmt="xlsx")
        self.assertEqual(["md", "csv", "html"], list(REPORT_FORMATS))


class BatchTrendSvgTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        report = create_project("趋势图测试", base=base / "projects")
        self.project = Path(report["path"])
        write_graph_data(self.project, make_graph("flow-trend"))

    def test_trend_svg_contains_bars_and_summary(self) -> None:
        trend = batch_trend_svg(self.project, limit=10)
        self.assertTrue(trend["ok"])
        self.assertIn("<svg", trend["svg"])
        self.assertIn("批次趋势", trend["svg"])
        self.assertGreaterEqual(trend["summary"]["batches"], 0)

    def test_trend_svg_empty_project(self) -> None:
        empty = Path(create_project("趋势空项目", base=Path(self._tmp.name) / "projects")["path"])
        trend = batch_trend_svg(empty, limit=5)
        self.assertIn("暂无批次数据", trend["svg"])


class BatchReportPushTest(unittest.TestCase):
    """M36：把批次报表摘要推送到 webhook（event=batch.report）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        report = create_project("报表推送", base=base / "projects")
        self.project = Path(report["path"])
        write_graph_data(self.project, make_graph("flow-a"))
        run_batch(self.project, ["flow-a"], dry_run=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_push_posts_report_event(self) -> None:
        captured: dict = {}

        class _FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"ok":true}'

        def fake_urlopen(request, timeout=10):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _FakeResponse()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            result = push_batch_report(self.project, webhook_url="https://example.test/hook", retries=0)
        self.assertTrue(result["ok"])
        self.assertTrue(result["webhook"]["ok"])
        self.assertEqual(200, result["webhook"]["status_code"])
        body = captured["body"]
        self.assertEqual("batch.report", body["event"])
        self.assertIn("summary", body)
        self.assertEqual("md", body["format"])
        self.assertIn("批次报表", body["message"])
        self.assertIn("批次趋势报表", body["text"])

    def test_push_requires_webhook_url(self) -> None:
        with self.assertRaises(FlowError) as ctx:
            push_batch_report(self.project, webhook_url="  ")
        self.assertIn("缺少 webhook 地址", str(ctx.exception))

    def test_push_unknown_format(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            push_batch_report(self.project, webhook_url="https://example.test/hook", fmt="xlsx")
        self.assertIn("未知报表格式", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
