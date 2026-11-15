"""项目快照与回滚（M18）：create/list/apply、安全快照、路径校验、发行包回滚演练。"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import rollback_drill  # noqa: E402
from cli.main import main  # noqa: E402
from core_router.project import ProjectError, create_project, load_state, save_state  # noqa: E402
from core_router.rollback import (  # noqa: E402
    METADATA_NAME,
    create_snapshot,
    list_snapshots,
    rollback_to,
    snapshot_path,
    snapshots_dir,
)


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class RollbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("回滚测试", base=self.base / "projects")
        self.project = Path(report["path"])

    def test_create_and_list(self) -> None:
        report = create_snapshot(self.project, "初始状态")
        self.assertTrue(report["ok"])
        self.assertRegex(report["snapshot_id"], r"^snap-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertTrue(Path(report["path"]).is_file())
        self.assertIn("00_project/state.json", report["files"])
        rows = list_snapshots(self.project)
        self.assertEqual(1, len(rows))
        self.assertEqual(report["snapshot_id"], rows[0]["snapshot_id"])
        self.assertEqual("初始状态", rows[0]["label"])

    def test_apply_restores_state(self) -> None:
        snapshot = create_snapshot(self.project, "before")
        original = load_state(self.project)
        changed = dict(original)
        changed["next_action"] = "回滚前被修改"
        save_state(self.project, changed)
        self.assertEqual("回滚前被修改", load_state(self.project)["next_action"])

        report = rollback_to(self.project, snapshot["snapshot_id"])
        self.assertTrue(report["ok"])
        self.assertFalse(report["dry_run"])
        self.assertIn("00_project/state.json", report["restored_files"])
        self.assertEqual(original["next_action"], load_state(self.project)["next_action"])
        self.assertRegex(report["safety_snapshot"], r"^snap-")

    def test_dry_run_does_not_write(self) -> None:
        snapshot = create_snapshot(self.project, "before")
        original = load_state(self.project)
        changed = dict(original)
        changed["next_action"] = "预演不应恢复"
        save_state(self.project, changed)
        before_list = list_snapshots(self.project)

        report = rollback_to(self.project, snapshot["snapshot_id"], dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual("预演不应恢复", load_state(self.project)["next_action"])
        self.assertEqual(len(before_list), len(list_snapshots(self.project)))

    def test_invalid_or_missing_snapshot(self) -> None:
        with self.assertRaises(ProjectError):
            rollback_to(self.project, "not-a-snapshot")
        with self.assertRaises(ProjectError):
            rollback_to(self.project, "snap-20260101-000000-abcd")
        with self.assertRaises(ProjectError):
            create_snapshot(self.project, snapshot_id="bad-id")

    def test_duplicate_snapshot_id_rejected(self) -> None:
        report = create_snapshot(self.project)
        with self.assertRaises(ProjectError):
            create_snapshot(self.project, snapshot_id=report["snapshot_id"])

    def test_corrupted_snapshot_metadata(self) -> None:
        directory = snapshots_dir(self.project)
        bad = directory / "snap-20260101-000000-abcd.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr(METADATA_NAME, "not json")
        with self.assertRaises(ProjectError):
            rollback_to(self.project, bad.stem.replace(".zip", ""))

    def test_path_traversal_rejected(self) -> None:
        sid = "snap-20260101-000000-abcd"
        path = snapshot_path(self.project, sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "contract_version": "1.0",
            "snapshot_id": sid,
            "project": "回滚测试",
            "state_version": 1,
            "stage": "01",
            "created_at": "2026-01-01T00:00:00+08:00",
            "label": "",
            "files": ["../evil.json"],
        }
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(METADATA_NAME, json.dumps(metadata, ensure_ascii=False))
        with self.assertRaises(ProjectError):
            rollback_to(self.project, sid)

    def test_cli_rollback_commands(self) -> None:
        report = create_snapshot(self.project, "CLI")
        code, out = run_cli(["rollback", "list", "--project", str(self.project), "--json"])
        self.assertEqual(0, code)
        payload = json.loads(out)
        self.assertEqual(1, payload["count"])
        self.assertEqual(report["snapshot_id"], payload["snapshots"][0]["snapshot_id"])

        code, out = run_cli(
            ["rollback", "apply", "--project", str(self.project), "--snapshot", report["snapshot_id"], "--json"]
        )
        self.assertEqual(0, code)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["dry_run"])


class RollbackDrillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.dist = self.base / "dist"
        self.dist.mkdir()
        for version in ("0.1.0", "0.2.0"):
            self._make_release(version)

    def _make_release(self, version: str) -> None:
        zip_path = self.dist / f"workbench-{version}.zip"
        script = (
            "from pathlib import Path\n"
            "print('workbench ' + (Path(__file__).resolve().parent / 'VERSION').read_text().strip())\n"
        )
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("workbench/workbench.py", script)
            archive.writestr("workbench/VERSION", version + "\n")

    def test_drill_upgrade_and_rollback(self) -> None:
        report = rollback_drill.drill(self.dist, workdir=self.base / "run")
        self.assertTrue(report["ok"])
        self.assertIn("0.1.0", report["installed_version"])
        self.assertIn("0.2.0", report["upgraded_version"])
        self.assertIn("0.1.0", report["rolled_back_version"])
        self.assertEqual(3, len(report["steps"]))

    def test_drill_requires_two_releases(self) -> None:
        only = self.base / "only"
        only.mkdir()
        shutil.copy(self.dist / "workbench-0.1.0.zip", only)
        with self.assertRaises(RuntimeError):
            rollback_drill.drill(only, workdir=self.base / "run2")


if __name__ == "__main__":
    unittest.main()
