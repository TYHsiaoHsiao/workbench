"""E2E 测试：从零走完 01-05、修订标记下游、旧项目迁移 + 规则升级。"""
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
from core_router.gates import (  # noqa: E402
    advance,
    can_advance,
    ensure_stage_gates,
    gate_detail,
    mark_downstream_stale,
    pass_gate,
)
from core_router.project import create_project, load_state, save_state  # noqa: E402
from core_router.registry import load_registry  # noqa: E402


class EndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "projects"
        self.base.mkdir()
        self.registry = load_registry()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_from_zero_through_stage_05(self) -> None:
        create_project("端到端短片", base=self.base)
        root = self.base / "端到端短片"
        state = load_state(root)
        stages = []
        while state["stage"] != "05":
            ensure_stage_gates(state, state["stage"], self.registry)
            for item in gate_detail(state, state["stage"], self.registry):
                pass_gate(state, item["id"], registry=self.registry)
            ok, reasons = can_advance(state, registry=self.registry)
            self.assertTrue(ok, reasons)
            stages.append(advance(state, registry=self.registry))
            save_state(root, state)
            state = load_state(root)
        self.assertEqual(stages, ["02", "04", "05"])
        self.assertEqual(state["stage"], "05")
        self.assertTrue((root / "状态卡.md").is_file())

    def test_revise_upstream_marks_downstream(self) -> None:
        create_project("修订项目", base=self.base)
        root = self.base / "修订项目"
        state = load_state(root)
        state["stage"] = "04"
        stale = mark_downstream_stale(state, "04", self.registry)
        self.assertEqual(stale, ["05", "06", "07", "08"])
        save_state(root, state)
        reloaded = load_state(root)
        self.assertEqual(reloaded["stale_downstream"], ["05", "06", "07", "08"])

    def test_cli_init_route_and_gate(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["init", "命令行项目", "--project-root", str(self.base), "--json"])
        self.assertEqual(code, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["stage"], "01")

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["route", "只做CINEDANCE"]), 0)
        self.assertIn("direct_entry", buf.getvalue())

        project = report["path"]
        for gate in ("positioning_menu", "sub_option_confirm"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(main(["gate", "pass", gate, "--project", project]), 0)

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["next", "--project", project]), 0)
        self.assertIn("02", buf.getvalue())

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(
                main(["check", "--project", project]), 0
            )
        self.assertIn("校验通过", buf.getvalue())

    def test_cli_next_blocked_returns_error(self) -> None:
        create_project("阻塞项目", base=self.base)
        project = str(self.base / "阻塞项目")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["next", "--project", project]), 1)
        self.assertIn("不能推进", buf.getvalue())

    def test_cli_migrate_and_upgrade(self) -> None:
        legacy = Path(self.tmp.name) / "老项目"
        (legacy / "00_project").mkdir(parents=True)
        (legacy / "00_project" / "state.json").write_text(
            json.dumps({"project": "老项目", "entry": "A", "stage": "02"}), encoding="utf-8"
        )
        (legacy / "00_project" / "project-status.md").write_text(
            "| 字段 | 值 |\n| 项目名称 | 老项目 |\n| 当前阶段 | 02 |\n", encoding="utf-8"
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["migrate", "--project", str(legacy), "--json"]), 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(report["stage"], "02")
        self.assertTrue((legacy / "00_project" / "reference-memory.json").is_file())

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["upgrade", "--project", str(legacy), "--json"]), 0)
        upgrade_report = json.loads(buf.getvalue())
        self.assertTrue(Path(upgrade_report["backup"]).is_dir())
        self.assertTrue((legacy / "AGENTS.md").is_file())


if __name__ == "__main__":
    unittest.main()
