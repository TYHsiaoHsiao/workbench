"""产物快照与差异（M7）：flow.artifacts + CLI project snapshot / artifacts-diff。"""
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
    create_snapshot,
    diff_snapshots,
    diff_with_current,
    format_diff_text,
    latest_snapshot,
    list_snapshots,
    read_snapshot,
)

cli_main = importlib.import_module("cli.main").main


class ArtifactsSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("快照测试", base=self.base / "projects")
        self.project = Path(report["path"])
        self.story = self.project / "01_story"
        self.story.mkdir(parents=True, exist_ok=True)
        self.synopsis = self.story / "synopsis.md"
        self.synopsis.write_text("# 大纲\n第一版\n", encoding="utf-8")

    def test_create_and_list_snapshot(self) -> None:
        record = create_snapshot(self.project, label="初版")
        self.assertTrue(record["snapshot_id"].startswith("snap-"))
        self.assertEqual(1, record["summary"]["count"])
        self.assertEqual(record["snapshot_id"], latest_snapshot(self.project)["snapshot_id"])
        self.assertEqual(1, len(list_snapshots(self.project)))
        loaded = read_snapshot(self.project, record["snapshot_id"])
        self.assertEqual("初版", loaded["label"])
        self.assertEqual("01_story/synopsis.md", loaded["files"][0]["path"])

    def test_diff_added_changed_removed(self) -> None:
        first = create_snapshot(self.project)
        self.synopsis.write_text("# 大纲\n第二版\n", encoding="utf-8")
        new_file = self.project / "02_script" / "screenplay.md"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("剧本\n", encoding="utf-8")
        diff = diff_with_current(self.project, first["snapshot_id"])
        self.assertEqual(1, diff["summary"]["changed"])
        self.assertEqual(1, diff["summary"]["added"])
        self.assertIn("# 大纲\n第二版", self.synopsis.read_text(encoding="utf-8"))
        self.assertIn("产物差异", format_diff_text(diff))

        second = create_snapshot(self.project)
        self.synopsis.unlink()
        diff2 = diff_snapshots(self.project, second["snapshot_id"], second["snapshot_id"])
        self.assertEqual(0, diff2["summary"]["changed"])

    def test_cli_snapshot_and_diff(self) -> None:
        code = cli_main(["project", "snapshot", "--project", str(self.project), "--label", "CLI 快照", "--json"])
        self.assertEqual(0, code)
        code = cli_main(["project", "snapshots", "--project", str(self.project), "--json"])
        self.assertEqual(0, code)
        code = cli_main(["project", "artifacts-diff", "--project", str(self.project), "--json"])
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
