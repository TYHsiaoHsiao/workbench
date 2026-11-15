"""跨阶段内容一致性检查：check --content。"""
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
from core_router.project import create_project, load_state, save_state  # noqa: E402


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class ContentCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("内容检查项目", base=self.base / "projects")
        self.project = Path(report["path"])

    def _write(self, relative: str, text: str) -> Path:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _update_state(self, **changes) -> None:
        state = load_state(self.project)
        state.update(changes)
        save_state(self.project, state)

    def _check(self) -> tuple[int, dict]:
        code, output = run_cli(["check", "--project", str(self.project), "--content", "--json"])
        return code, json.loads(output)

    def test_clean_project_passes(self) -> None:
        code, report = self._check()
        self.assertEqual(0, code, msg=report)
        self.assertEqual([], report["errors"])
        self.assertTrue(report["ok"])

    def test_missing_style_card_detected(self) -> None:
        self._update_state(style={
            "status": "on",
            "profile_path": "00_project/style-cards/missing.json",
            "note": "风格 002",
        })
        code, report = self._check()
        self.assertEqual(1, code)
        self.assertTrue(any("风格卡文件不存在" in item for item in report["errors"]), msg=report)

    def test_missing_artifact_file_detected(self) -> None:
        self._update_state(stage_artifacts={"01": "01_story/missing.md"})
        code, report = self._check()
        self.assertEqual(1, code)
        self.assertTrue(any("引用的文件不存在" in item for item in report["errors"]), msg=report)

    def test_bridge_status_without_card_detected(self) -> None:
        self._update_state(knowledge_bridge={
            "status": "requested",
            "last_card": "00_project/knowledge-cards/01-candidates.json",
            "confirmed_references": [],
            "note": "",
        })
        code, report = self._check()
        self.assertEqual(1, code)
        self.assertTrue(any("知识卡文件不存在" in item for item in report["errors"]), msg=report)

    def test_bridge_confirmed_not_subset_detected(self) -> None:
        card = self._write("00_project/knowledge-cards/01-candidates.json", "{}")
        self.assertTrue(card.is_file())
        self._update_state(knowledge_bridge={
            "status": "on",
            "last_card": "00_project/knowledge-cards/01-candidates.json",
            "confirmed_references": ["参考方法001"],
            "note": "",
        })
        code, report = self._check()
        self.assertEqual(1, code)
        self.assertTrue(any("不在 state.references" in item for item in report["errors"]),
                        msg=report)

    def test_duration_mismatch_detected(self) -> None:
        self._write("01_story/treatment.md",
                    "| 场次 | 内容 | 时长 |\n| --- | --- | --- |\n| 1-01 | 开场 | 3s |\n")
        self._write("05_shots/1-01-shot-plan-v01.md", "场次时长预算：10s\n")
        code, report = self._check()
        self.assertEqual(1, code)
        self.assertTrue(any("时长不一致" in item for item in report["errors"]), msg=report)

    def test_stale_downstream_is_warning(self) -> None:
        self._update_state(stale_downstream=["06", "07"])
        code, report = self._check()
        self.assertEqual(0, code, msg=report)
        self.assertTrue(any("stale_downstream" in item for item in report["warnings"]), msg=report)


if __name__ == "__main__":
    unittest.main()
