"""产物登记与知识桥状态：register_artifacts / update_knowledge_bridge。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main  # noqa: E402
from core_router import register_artifacts, update_knowledge_bridge  # noqa: E402
from core_router.project import ProjectError, create_project, load_state, save_state  # noqa: E402


def run_cli(argv: list[str]) -> tuple[int, str]:
    import io
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class ArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("产物登记项目", base=self.base / "projects")
        self.project = Path(report["path"])

    def _write(self, relative: str, text: str) -> Path:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_register_updates_state_and_revision(self) -> None:
        self._write("01_story/synopsis.md", "# 大纲 v01\n")
        report = register_artifacts(self.project, "01", "大纲", ["01_story/synopsis.md"])
        self.assertTrue(report["ok"])
        self.assertEqual(1, len(report["files"]))
        self.assertEqual(64, len(report["files"][0]["sha256"]))
        self.assertIn("大纲：1 个文件", report["summary"])
        state = load_state(self.project)
        self.assertIn("大纲：1 个文件", state["stage_artifacts"]["01"])
        self.assertEqual("artifact_registered", state["revision_log"][-1]["action"])
        self.assertEqual("01", state["revision_log"][-1]["stage"])

    def test_register_glob_and_absolute_path(self) -> None:
        self._write("01_story/a.md", "A")
        self._write("01_story/b.md", "B")
        report = register_artifacts(self.project, "01", "故事",
                                    ["01_story/*.md", str(self.project / "01_story" / "a.md")])
        self.assertEqual(2, len(report["files"]))
        self.assertEqual([], report["missing"])

    def test_register_missing_file_raises(self) -> None:
        with self.assertRaises(ProjectError):
            register_artifacts(self.project, "01", "大纲", ["01_story/nope.md"])

    def test_register_outside_project_raises(self) -> None:
        outside = self.base / "outside.md"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(ProjectError):
            register_artifacts(self.project, "01", "大纲", [str(outside)])

    def test_register_done_stage_allowed(self) -> None:
        self._write("00_inbox/delivery.txt", "交付")
        report = register_artifacts(self.project, "done", "交付", ["00_inbox/delivery.txt"])
        self.assertTrue(report["ok"])
        state = load_state(self.project)
        self.assertIn("done", state["stage_artifacts"])

    def test_register_bad_stage_raises(self) -> None:
        with self.assertRaises(ProjectError):
            register_artifacts(self.project, "09", "大纲", [])

    def test_update_knowledge_bridge_merges(self) -> None:
        report = update_knowledge_bridge(
            self.project, "requested",
            last_card="00_project/knowledge-cards/01-candidates.json",
            confirmed_references=["参考方法001"],
        )
        self.assertTrue(report["ok"])
        self.assertEqual("requested", report["knowledge_bridge"]["status"])
        self.assertEqual(["参考方法001"], report["knowledge_bridge"]["confirmed_references"])
        state = load_state(self.project)
        self.assertEqual("requested", state["knowledge_bridge"]["status"])

    def test_update_knowledge_bridge_rejects_bad_status(self) -> None:
        with self.assertRaises(ProjectError):
            update_knowledge_bridge(self.project, "enabled")

    def test_cli_artifact_register(self) -> None:
        self._write("01_story/synopsis.md", "# 大纲\n")
        code, output = run_cli([
            "artifact", "register", "--project", str(self.project),
            "--stage", "01", "--kind", "大纲",
            "--path", "01_story/synopsis.md", "--json",
        ])
        self.assertEqual(0, code, msg=output)
        report = json.loads(output)
        self.assertTrue(report["ok"])
        self.assertEqual(1, len(report["files"]))


if __name__ == "__main__":
    unittest.main()
