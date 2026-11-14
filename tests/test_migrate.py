"""旧项目迁移与规则升级测试：备份、状态合并、参考记忆 MD -> JSON、创作文件不变。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.migrate import (  # noqa: E402
    MigrationError,
    migrate_project,
    upgrade_project_rules,
)
from core_router.project import load_state  # noqa: E402
from contracts import validate  # noqa: E402


LEGACY_MEMORY = """# 跨阶段参考记忆

状态：启用
知识库外挂状态：已调用
下一参考编号：参考方法003

## 参考方法001
- 来源名称：某编剧方法书
- 来源类型：method_book
- 本地路径：08-编剧方法书籍/示例.md
- 页码与命中词：第 12 页「结构」
- 可迁移方法：三幕式节奏
- 使用范围：故事创作（01-05）
- 状态：启用

## 参考方法002
- 来源名称：某获奖剧本
- 来源类型：reference_script
- 本地路径：05-类型片/示例.md
- 页码与命中词：第 3 行「反转」
- 可迁移方法：悬念回收
- 使用范围：表演
- 状态：停用
"""


class MigrateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "旧项目"
        project = self.root / "00_project"
        project.mkdir(parents=True)
        (self.root / "01_story").mkdir()
        self.creative = self.root / "01_story" / "synopsis.md"
        self.creative.write_text("作者原文，不可改动", encoding="utf-8")

        legacy_state = {
            "contract_version": "1.0",
            "project": "旧项目",
            "entry": "C",
            "mode": "full",
            "stage": "03",
            "version": "v05",
            "authoritative_inputs": ["作者剧本"],
            "references": [],
            "gates": [],
            "stale_downstream": ["04"],
            "next_action": "继续世界观",
        }
        (project / "state.json").write_text(
            json.dumps(legacy_state, ensure_ascii=False), encoding="utf-8"
        )
        (project / "brief.md").write_text("# 一句话需求\n\n旧项目\n", encoding="utf-8")
        (project / "project-status.md").write_text(
            "# 项目状态卡\n\n| 字段 | 值 |\n|---|---|\n| 项目名称 | 旧项目 |\n"
            "| 入口 | C |\n| 当前阶段 | 03 |\n| 本轮权威输入 | 作者剧本、参考资料 |\n",
            encoding="utf-8",
        )
        (project / "routing.md").write_text(
            "# 路由\n\n项目入口：C\n当前阶段：03\n", encoding="utf-8"
        )
        (project / "reference-memory.md").write_text(LEGACY_MEMORY, encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# 旧项目规则\n", encoding="utf-8")
        (self.root / "状态卡.md").write_text("# 旧状态卡\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_migrate_merges_state_and_memory(self) -> None:
        report = migrate_project(self.root)
        self.assertTrue(report["ok"])
        self.assertEqual(report["stage"], "03")
        self.assertEqual(report["entry"], "C")
        self.assertEqual(report["reference_entries"], 2)
        self.assertEqual(report["legacy_memory_retired"], "reference-memory.md")
        self.assertTrue(Path(report["backup"]).is_dir())
        self.assertEqual(
            (self.creative).read_text(encoding="utf-8"), "作者原文，不可改动"
        )

        state = load_state(self.root)
        self.assertEqual(state["stage"], "03")
        self.assertEqual(state["entry"], "C")
        self.assertEqual(state["version"], "v05")
        self.assertEqual(validate(state, schema_name="state.schema.json"), [])
        self.assertEqual(state["gates"][0]["stage"], "03")

        memory = json.loads(
            (self.root / "00_project" / "reference-memory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(validate(memory, schema_name="reference-memory.schema.json"), [])
        entries = {entry["id"]: entry for entry in memory["entries"]}
        self.assertEqual(entries["参考方法001"]["status"], "enabled")
        self.assertEqual(entries["参考方法001"]["scope"], ["story_01_05"])
        self.assertEqual(entries["参考方法002"]["status"], "disabled")
        self.assertEqual(entries["参考方法002"]["scope"], ["performance_07"])
        self.assertTrue((self.root / "00_project" / "reference-memory.legacy.md").is_file())
        self.assertFalse((self.root / "00_project" / "reference-memory.md").exists())
        self.assertTrue((self.root / "00_project" / "migration-report.md").is_file())

    def test_migrate_requires_project_dir(self) -> None:
        with self.assertRaises(MigrationError):
            migrate_project(Path(self.tmp.name) / "空目录")

    def test_upgrade_project_rules(self) -> None:
        migrate_project(self.root)
        (self.root / "AGENTS.md").write_text("# 自定义旧规则\n", encoding="utf-8")
        report = upgrade_project_rules(self.root)
        self.assertTrue(report["ok"])
        self.assertIn("AGENTS.md", report["backed_up"])
        backup = Path(report["backup"])
        self.assertTrue((backup / "AGENTS.md").is_file())
        self.assertIn("工作台", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue((self.root / "00_project" / "upgrade-report.md").is_file())
        self.assertEqual(
            (self.creative).read_text(encoding="utf-8"), "作者原文，不可改动"
        )
        state = load_state(self.root)
        self.assertEqual(state["stage"], "03")

    def test_upgrade_requires_state(self) -> None:
        bare = Path(self.tmp.name) / "无状态项目"
        (bare / "00_project").mkdir(parents=True)
        with self.assertRaises(MigrationError):
            upgrade_project_rules(bare)


if __name__ == "__main__":
    unittest.main()
