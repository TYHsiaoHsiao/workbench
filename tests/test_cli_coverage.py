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
