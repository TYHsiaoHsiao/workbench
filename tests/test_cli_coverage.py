"""CLI 广覆盖测试（M23）：以 in-process 方式驱动更多子命令，提升 CLI 覆盖率。"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main  # noqa: E402


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _json(run: tuple[int, str]) -> dict:
    code, output = run
    if code != 0:
        raise AssertionError(f"exit={code}\n{output}")
    return json.loads(output)


def _json_any(run: tuple[int, str], allowed=(0, 1)) -> dict:
    code, output = run
    if code not in allowed:
        raise AssertionError(f"exit={code}\n{output}")
    return json.loads(output)


class CliCoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.project = self.root / "覆盖项目"
        code, output = run_cli(["init", "覆盖项目", "--project-root", str(self.root)])
        self.assertEqual(0, code, msg=output)
        code, output = run_cli(
            ["flow", "new", "--project", str(self.project), "--template", "tpl-full-flow",
             "--name", "覆盖流程", "--graph", "flow-cover"]
        )
        self.assertEqual(0, code, msg=output)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_route_gate_next(self) -> None:
        data = _json(run_cli(["route", "帮我写第一幕剧本", "--json"]))
        self.assertIn("kind", data)
        code, output = run_cli(["gate", "list", "--project", str(self.project), "--json"])
        self.assertEqual(0, code, msg=output)
        gates = json.loads(output)["gates"]
        self.assertTrue(gates)
        code, output = run_cli(["next", "--project", str(self.project)])
        self.assertIn(code, (0, 1), msg=output)

    def test_project_ops(self) -> None:
        _json(run_cli(["project", "list", "--json"]))
        data = _json(run_cli(["project", "summary", "--project", str(self.project), "--json"]))
        self.assertTrue(data["ok"])
        snap1 = _json(run_cli(["project", "snapshot", "--project", str(self.project), "--label", "s1", "--json"]))
        snap2 = _json(run_cli(["project", "snapshot", "--project", str(self.project), "--label", "s2", "--json"]))
        sid1 = snap1["snapshot"]["snapshot_id"]
        sid2 = snap2["snapshot"]["snapshot_id"]
        snaps = _json(run_cli(["project", "snapshots", "--project", str(self.project), "--json"]))
        self.assertGreaterEqual(len(snaps["snapshots"]), 2)
        _json(run_cli(["project", "artifacts-diff", "--project", str(self.project),
                       "--base", sid1, "--target", sid2, "--json"]))
        _json(run_cli(["rollback", "create", "--project", str(self.project), "--label", "r1", "--json"]))
        _json(run_cli(["rollback", "list", "--project", str(self.project), "--json"]))

    def test_flow_graph_ops(self) -> None:
        _json(run_cli(["flow", "templates", "--json"]))
        listed = _json(run_cli(["flow", "list", "--project", str(self.project), "--json"]))
        self.assertTrue(listed["graphs"])
        _json(run_cli(["flow", "show", "--project", str(self.project), "--graph", "flow-cover", "--json"]))
        _json(run_cli(["flow", "validate", "--project", str(self.project), "--graph", "flow-cover", "--json"]))
        out_file = self.root / "flow-export.json"
        code, output = run_cli(["flow", "export", "--project", str(self.project), "--graph", "flow-cover",
                                "--out", str(out_file)])
        self.assertEqual(0, code, msg=output)
        self.assertTrue(out_file.is_file())
        _json(run_cli(["flow", "import", "--project", str(self.project), "--file", str(out_file),
                       "--graph", "flow-imported", "--force", "--json"]))
        run1 = _json_any(run_cli(["flow", "run", "--project", str(self.project), "--graph", "flow-cover",
                                  "--dry-run", "--yes", "--json"]))
        run2 = _json_any(run_cli(["flow", "run", "--project", str(self.project), "--graph", "flow-cover",
                                  "--dry-run", "--yes", "--json"]))
        run_id1 = run1["run"]["run_id"]
        run_id2 = run2["run"]["run_id"]
        _json(run_cli(["flow", "runs", "--project", str(self.project), "--json"]))
        _json(run_cli(["flow", "replay", "--project", str(self.project), "--run", run_id1, "--json"]))
        _json(run_cli(["flow", "diff", "--project", str(self.project), "--run", run_id1,
                       "--other-run", run_id2, "--json"]))
        _json(run_cli(["flow", "baseline", "set", "--project", str(self.project), "--graph", "flow-cover",
                       "--run", run_id1, "--json"]))
        _json(run_cli(["flow", "baseline", "show", "--project", str(self.project), "--graph", "flow-cover", "--json"]))
        _json(run_cli(["flow", "baseline", "clear", "--project", str(self.project), "--graph", "flow-cover", "--json"]))

    def test_batch_queue_cli(self) -> None:
        batch = _json_any(run_cli(["flow", "batch", "--project", str(self.project), "--all",
                                   "--dry-run", "--json"]))
        batch_id = batch["batch"]["batch_id"]
        _json(run_cli(["flow", "batches", "--project", str(self.project), "--json"]))
        _json(run_cli(["flow", "batch-show", "--project", str(self.project), "--batch", batch_id, "--json"]))
        code, output = run_cli(["flow", "batch-recover", "--project", str(self.project),
                                "--batch", batch_id, "--json"])
        self.assertIn(code, (0, 1), msg=output)
        _json(run_cli(["flow", "queue", "add", "--project", str(self.project), "--all", "--dry-run", "--json"]))
        _json(run_cli(["flow", "queue", "add", "--project", str(self.project), "--all", "--dry-run", "--json"]))
        entries = _json(run_cli(["flow", "queue", "list", "--project", str(self.project), "--json"]))
        self.assertGreaterEqual(len(entries["entries"]), 2)
        qid = entries["entries"][-1]["queue_id"]
        _json(run_cli(["flow", "queue", "move", qid, "--project", str(self.project), "--index", "0", "--json"]))
        _json(run_cli(["flow", "queue", "cancel", qid, "--project", str(self.project), "--json"]))
        code, output = run_cli(["flow", "queue", "run", "--project", str(self.project), "--limit", "1", "--json"])
        self.assertIn(code, (0, 1), msg=output)
        _json(run_cli(["flow", "queue", "notifications", "--project", str(self.project), "--json"]))
        alerts = _json(run_cli(["flow", "queue", "alerts", "--project", str(self.project), "--json"]))
        self.assertIn("count", alerts)
        code, output = run_cli(["flow", "queue", "daemon", "--project", str(self.project),
                                "--until-empty", "--interval", "1", "--limit", "1"])
        self.assertEqual(0, code, msg=output)

    def test_m31_cron_and_alerts(self) -> None:
        preview = _json(run_cli(["flow", "cron-preview", "--expression", "*/5 * * * *", "--count", "3", "--json"]))
        self.assertTrue(preview["ok"])
        self.assertEqual(3, len(preview["next"]))
        code, _ = run_cli(["flow", "cron-preview", "--expression", "bad expr", "--json"])
        self.assertEqual(1, code)
        alerts = _json(run_cli(["flow", "queue", "alerts", "--project", str(self.project), "--json"]))
        self.assertEqual(0, alerts["count"])

    def test_m32_alerts_push_and_exit(self) -> None:
        from unittest import mock

        code, _ = run_cli(["flow", "queue", "alerts", "--project", str(self.project),
                           "--fail-if-failures", "--json"])
        self.assertEqual(0, code)
        notif = self.project / "00_project" / "workflows" / "queue-notifications.jsonl"
        notif.parent.mkdir(parents=True, exist_ok=True)
        notif.write_text(
            '{"at": "2026-11-16T09:00:00", "status": "failed", "message": "x", "failed_graphs": ["g1"]}\n',
            encoding="utf-8",
        )
        code, _ = run_cli(["flow", "queue", "alerts", "--project", str(self.project),
                           "--fail-if-failures", "--json"])
        self.assertEqual(2, code)
        captured: dict = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b"{}"

        def fake_urlopen(request, timeout=10):
            captured["body"] = request.data
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            code, output = run_cli(["flow", "queue", "alerts", "--project", str(self.project),
                                    "--webhook-url", "http://example.test/hook", "--json"])
        self.assertEqual(0, code, msg=output)
        data = json.loads(output)
        self.assertTrue(data["webhook"]["ok"])
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("queue.alerts.digest", body["event"])
        self.assertEqual(["g1"], body["failed_graphs"])

    def test_m33_batch_report_and_webhook_format(self) -> None:
        from unittest import mock

        _json_any(run_cli(["flow", "batch", "--project", str(self.project), "--all", "--dry-run", "--json"]))
        report = _json(run_cli(["flow", "batch-report", "--project", str(self.project),
                                "--limit", "5", "--json"]))
        self.assertIn("summary", report)
        out = self.root / "report.md"
        code, _ = run_cli(["flow", "batch-report", "--project", str(self.project),
                           "--format", "md", "--out", str(out)])
        self.assertEqual(0, code)
        self.assertTrue(out.is_file())
        self.assertIn("批次趋势报表", out.read_text(encoding="utf-8"))
        code, _ = run_cli(["flow", "batch-report", "--project", str(self.project),
                           "--format", "csv", "--out", str(self.root / "report.csv")])
        self.assertEqual(0, code)

        out_html = self.root / "report.html"
        code, _ = run_cli(["flow", "batch-report", "--project", str(self.project),
                           "--format", "html", "--out", str(out_html)])
        self.assertEqual(0, code)
        html_text = out_html.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", html_text)
        self.assertIn('class="bar-fill', html_text)

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        captured: dict = {}

        def fake_urlopen(request, timeout=10):
            captured["body"] = request.data
            return FakeResponse()

        notif = self.project / "00_project" / "workflows" / "queue-notifications.jsonl"
        notif.parent.mkdir(parents=True, exist_ok=True)
        notif.write_text(
            '{"at": "2026-11-16T09:00:00", "status": "failed", "message": "x", "failed_graphs": ["g1", "g2"]}\n',
            encoding="utf-8",
        )
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            code, output = run_cli(
                ["flow", "queue", "alerts", "--project", str(self.project),
                 "--webhook-url", "http://example.test/hook", "--webhook-format", "feishu",
                 "--webhook-retries", "1", "--json"]
            )
        self.assertEqual(0, code, msg=output)
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("text", body["msg_type"])
        self.assertIn("g1、g2", body["content"]["text"])

    def test_m37_batch_trend_and_feishu_card(self) -> None:
        from unittest import mock

        _json_any(run_cli(["flow", "batch", "--project", str(self.project), "--all", "--dry-run", "--json"]))
        trend = _json(run_cli(["flow", "batch-trend", "--project", str(self.project), "--limit", "5", "--json"]))
        self.assertTrue(trend["ok"])
        self.assertGreater(trend["svg_chars"], 100)
        svg_out = self.root / "trend.svg"
        code, _ = run_cli(["flow", "batch-trend", "--project", str(self.project),
                           "--limit", "5", "--out", str(svg_out)])
        self.assertEqual(0, code)
        self.assertIn("<svg", svg_out.read_text(encoding="utf-8"))

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        captured: dict = {}

        def fake_urlopen(request, timeout=10):
            captured["body"] = request.data
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            code, output = run_cli(
                ["flow", "batch-report", "--project", str(self.project), "--push",
                 "--webhook-url", "http://example.test/hook", "--webhook-format", "feishu_card", "--json"]
            )
        self.assertEqual(0, code, msg=output)
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual("interactive", body["msg_type"])
        self.assertEqual("batch.report", body["card"]["header"]["title"]["content"].split("·")[-1].strip())

    def test_index_and_knowledge_cli(self) -> None:
        source = self.root / "kb"
        source.mkdir()
        (source / "01-故事.md").write_text("# 第一幕\n建立悬念并介绍主角。\n", encoding="utf-8")
        (source / "02-方法.md").write_text("# 方法\n冲突升级与回收伏笔。\n", encoding="utf-8")
        out = self.root / "index"
        _json(run_cli(["index", "build", "--source", str(source), "--out", str(out), "--json"]))
        _json(run_cli(["index", "info", "--out", str(out), "--json"]))
        _json(run_cli(["index", "verify", "--out", str(out), "--json"]))
        hit = _json(run_cli(["index", "search", "--out", str(out), "--query", "建立悬念", "--json"]))
        self.assertGreaterEqual(hit["count"], 1)
        code, _ = run_cli(["index", "info", "--out", str(self.root / "no-index")])
        self.assertEqual(1, code)
        code, _ = run_cli(["knowledge", "probe", "--json"])
        self.assertIn(code, (0, 1, 3))

    def test_generate_cli(self) -> None:
        _json(run_cli(["generate", "providers", "--json"]))
        _json(run_cli(["generate", "plan", "mock", "--project", str(self.project),
                       "--prompt", "测试提示词", "--json"]))
        _json(run_cli(["generate", "submit", "mock", "--project", str(self.project),
                       "--prompt", "测试提示词", "--json"]))
        jobs = _json(run_cli(["generate", "jobs", "--project", str(self.project), "--json"]))
        self.assertTrue(jobs["jobs"])
        job_id = jobs["jobs"][0]["job_id"]
        code, output = run_cli(["generate", "show", job_id, "--project", str(self.project)])
        self.assertEqual(0, code, msg=output)
        code, output = run_cli(["generate", "refresh", "--project", str(self.project), "--all", "--json"])
        self.assertIn(code, (0, 1), msg=output)


class M38PracticalTest(unittest.TestCase):
    """M38：quickstart 与 practical-check 的实操入口。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_quickstart_creates_project_and_graph(self) -> None:
        data = _json(run_cli(["quickstart", "实操项目", "--project-root", str(self.root), "--json"]))
        self.assertTrue(data["ok"])
        self.assertTrue(data["created"])
        self.assertEqual("flow-main", data["graph_id"])
        self.assertEqual(1, data["graphs_count"])
        project = Path(data["project"])
        self.assertTrue((project / "00_project" / "state.json").is_file())
        self.assertTrue((project / "00_project" / "workflows" / "flow-main.json").is_file())
        self.assertIn("practical-check", " ".join(data["next_commands"]))

    def test_quickstart_rerun_is_idempotent(self) -> None:
        first = _json(run_cli(["quickstart", "复用项目", "--project-root", str(self.root), "--json"]))
        second = _json(run_cli(["quickstart", "复用项目", "--project-root", str(self.root), "--json"]))
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["project"], second["project"])

    def test_quickstart_skip_graph(self) -> None:
        data = _json(
            run_cli(["quickstart", "跳过图", "--project-root", str(self.root), "--skip-graph", "--json"])
        )
        self.assertEqual(0, data["graphs_count"])
        self.assertEqual("", data["graph_id"])

    def test_practical_check_ok_and_json(self) -> None:
        _json(run_cli(["quickstart", "自检项目", "--project-root", str(self.root), "--json"]))
        project = self.root / "自检项目"
        data = _json_any(run_cli(["practical-check", "--project", str(project), "--json"]))
        self.assertTrue(data["ok"])
        ids = {item["id"] for item in data["checks"]}
        self.assertTrue({"project", "registry", "flow", "style", "generate"} <= ids)
        self.assertEqual(0, data["summary"]["fail"])
        self.assertTrue(data["next_commands"])

    def test_practical_check_missing_project(self) -> None:
        code, _ = run_cli(["practical-check", "--project", str(self.root / "不存在")])
        self.assertEqual(1, code)

    def test_practical_check_without_graph_warns(self) -> None:
        _json(run_cli(["quickstart", "无图项目", "--project-root", str(self.root),
                       "--skip-graph", "--json"]))
        data = _json_any(run_cli(["practical-check", "--project", str(self.root / "无图项目"),
                                  "--json"]))
        self.assertTrue(data["ok"])
        flow_check = next(item for item in data["checks"] if item["id"] == "flow")
        self.assertEqual("warn", flow_check["status"])

class M39PracticalFixTest(unittest.TestCase):
    """M39：quickstart --demo 演示素材与 practical-check --fix 自动修复。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_quickstart_demo_creates_assets(self) -> None:
        data = _json(
            run_cli(["quickstart", "演示项目", "--project-root", str(self.root), "--demo", "--json"])
        )
        self.assertTrue(data["ok"])
        project = Path(data["project"])
        story = project / "01_story" / "演示剧本-午夜来电.md"
        prompt = project / "05_shots" / "shot-01-prompt.md"
        self.assertTrue(story.is_file())
        self.assertTrue(prompt.is_file())
        self.assertIn("01_story/演示剧本-午夜来电.md", data["demo_files"])
        self.assertIn("05_shots/shot-01-prompt.md", data["demo_files"])
        self.assertIn("午夜来电", story.read_text(encoding="utf-8"))
        self.assertIn("竖屏", prompt.read_text(encoding="utf-8"))

    def test_quickstart_demo_is_idempotent(self) -> None:
        first = _json(
            run_cli(["quickstart", "演示复用", "--project-root", str(self.root), "--demo", "--json"])
        )
        project = Path(first["project"])
        story = project / "01_story" / "演示剧本-午夜来电.md"
        original = story.read_text(encoding="utf-8")
        second = _json(
            run_cli(["quickstart", "演示复用", "--project-root", str(self.root), "--demo", "--json"])
        )
        self.assertEqual([], second["demo_files"])
        self.assertEqual(original, story.read_text(encoding="utf-8"))

    def test_practical_check_fix_creates_default_flow(self) -> None:
        _json(
            run_cli(["quickstart", "待修复", "--project-root", str(self.root),
                     "--skip-graph", "--json"])
        )
        project = self.root / "待修复"
        data = _json_any(
            run_cli(["practical-check", "--project", str(project), "--fix", "--json"])
        )
        fixes = {item["id"]: item for item in data["fixes"]}
        self.assertTrue(fixes["flow"]["ok"])
        self.assertIn("创建默认流程图", fixes["flow"]["detail"])
        flow_check = next(item for item in data["checks"] if item["id"] == "flow")
        self.assertEqual("ok", flow_check["status"])
        self.assertTrue((project / "00_project" / "workflows" / "flow-main.json").is_file())

    def test_practical_check_fix_keeps_existing_graph(self) -> None:
        _json(run_cli(["quickstart", "已有图", "--project-root", str(self.root), "--json"]))
        project = self.root / "已有图"
        data = _json_any(
            run_cli(["practical-check", "--project", str(project), "--fix", "--json"])
        )
        fixes = {item["id"]: item for item in data["fixes"]}
        self.assertEqual("已有流程图，无需修复", fixes["flow"]["detail"])

    def test_practical_check_fix_reports_index_skipped(self) -> None:
        _json(run_cli(["quickstart", "索引跳过", "--project-root", str(self.root), "--json"]))
        project = self.root / "索引跳过"
        data = _json_any(
            run_cli(["practical-check", "--project", str(project), "--fix", "--json"])
        )
        fixes = {item["id"]: item for item in data["fixes"]}
        # 本仓库可能已构建索引，也可能未构建；无论哪种都要有 index 修复项
        self.assertIn("index", fixes)

    def test_practical_check_fix_missing_project(self) -> None:
        code, _ = run_cli(["practical-check", "--project", str(self.root / "不存在"), "--fix"])
        self.assertEqual(1, code)
