"""安装器测试：安装、升级保留配置、备份、演练与失败回滚。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from installer import (  # noqa: E402
    Installer,
    InstallerError,
    install_skills,
    plan_install,
)


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.source = base / "source"
        self.target = base / "skills"
        for name in ("skill-a", "skill-b"):
            skill = self.source / name
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
            (skill / "references" / "note.txt").write_text("v1", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_plan_lists_skills(self) -> None:
        plan = plan_install(self.source, self.target)
        self.assertEqual(plan["skills"], ["skill-a", "skill-b"])
        self.assertEqual(Path(plan["target"]), self.target)

    def test_install_fresh(self) -> None:
        report = install_skills(self.source, target=self.target)
        self.assertEqual(report["installed"], ["skill-a", "skill-b"])
        self.assertEqual(report["backed_up"], [])
        self.assertTrue((self.target / "skill-a" / "SKILL.md").is_file())
        self.assertTrue((self.target / "skill-b" / "references" / "note.txt").is_file())

    def test_dry_run_writes_nothing(self) -> None:
        report = install_skills(self.source, target=self.target, dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse(self.target.exists())

    def test_upgrade_backs_up_and_preserves_config(self) -> None:
        install_skills(self.source, target=self.target)
        config = self.target / "skill-a" / "references" / "knowledge-base.json"
        config.write_bytes(b'{"database": "custom"}')
        (self.target / "skill-a" / "old-only.txt").write_text("old", encoding="utf-8")

        report = install_skills(self.source, target=self.target)
        self.assertEqual(report["backed_up"], ["skill-a", "skill-b"])
        self.assertIn("skill-a", report["preserved"])
        self.assertEqual(config.read_bytes(), b'{"database": "custom"}')
        self.assertFalse((self.target / "skill-a" / "old-only.txt").exists())
        backup = Path(report["backup"])
        self.assertTrue((backup / "skill-a" / "old-only.txt").is_file())

    def test_rollback_on_failure(self) -> None:
        install_skills(self.source, target=self.target)
        (self.target / "skill-a" / "marker.txt").write_text("old", encoding="utf-8")

        calls = {"count": 0}

        def hook(skill: Path) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("模拟复制失败")

        with self.assertRaises(InstallerError) as ctx:
            install_skills(self.source, target=self.target, copy_hook=hook)
        self.assertIn("回滚", str(ctx.exception))
        # 旧版本已恢复。
        self.assertEqual(
            (self.target / "skill-a" / "marker.txt").read_text(encoding="utf-8"), "old"
        )

    def test_invalid_source(self) -> None:
        with self.assertRaises(InstallerError):
            install_skills(self.source / "不存在", target=self.target)
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        with self.assertRaises(InstallerError):
            install_skills(empty, target=self.target)

    def test_health(self) -> None:
        health = Installer().health()
        self.assertTrue(health["implemented"])
        self.assertEqual(health["target_iteration"], "1b")


if __name__ == "__main__":
    unittest.main()
