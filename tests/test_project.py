"""项目初始化与状态存取测试：目录模板、状态契约、参考记忆、默认路径。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from contracts import load_schema, validate  # noqa: E402
from core_router.project import (  # noqa: E402
    PROJECT_DIRS,
    ProjectError,
    build_state,
    create_project,
    default_projects_root,
    detect_documents_dir,
    export_project,
    load_state,
    refresh_status_card,
    restore_project,
    save_state,
    state_path,
    workbench_home,
)
from core_router.state import validate_state  # noqa: E402


class ProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "projects"
        self.base.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_project_layout_and_files(self) -> None:
        report = create_project("测试项目", base=self.base, entry="C", mode="stage")
        root = self.base / "测试项目"
        self.assertEqual(report["stage"], "01")
        self.assertEqual(report["entry"], "C")
        self.assertEqual(report["mode"], "stage")
        for rel in PROJECT_DIRS:
            self.assertTrue((root / rel).is_dir(), rel)
        for name in ("00_project/state.json", "00_project/brief.md",
                     "00_project/reference-memory.json", "00_project/reference-memory.md",
                     "AGENTS.md", "状态卡.md"):
            self.assertTrue((root / name).is_file(), name)

    def test_state_matches_contract(self) -> None:
        create_project("契约项目", base=self.base)
        state = load_state(self.base / "契约项目")
        self.assertEqual(validate(state, schema_name="state.schema.json"), [])
        self.assertEqual(state["contract_version"], "1.0")
        self.assertEqual(state["stage"], "01")
        self.assertEqual(state["version"], "v01")
        self.assertEqual(state["knowledge_bridge"]["status"], "off")
        self.assertTrue(state["revision_log"])

    def test_reference_memory_json_contract(self) -> None:
        create_project("记忆项目", base=self.base)
        data = json.loads(
            (self.base / "记忆项目" / "00_project" / "reference-memory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["contract_version"], "1.0")
        self.assertEqual(data["entries"], [])
        self.assertEqual(validate(data, schema_name="reference-memory.schema.json"), [])

    def test_existing_project_requires_force(self) -> None:
        root = self.base / "重复项目"
        create_project("重复项目", base=self.base)
        marker = root / "00_project" / "brief.md"
        marker.write_text("用户内容", encoding="utf-8")
        with self.assertRaises(ProjectError):
            create_project("重复项目", base=self.base)
        report = create_project("重复项目", base=self.base, force=True)
        self.assertTrue(report["overwritten"])
        self.assertNotEqual(marker.read_text(encoding="utf-8"), "用户内容")

    def test_empty_name_rejected(self) -> None:
        with self.assertRaises(ProjectError):
            create_project("   ", base=self.base)

    def test_load_state_errors(self) -> None:
        with self.assertRaises(ProjectError):
            load_state(self.base / "不存在")
        root = self.base / "坏状态"
        (root / "00_project").mkdir(parents=True)
        (root / "00_project" / "state.json").write_text("{bad json", encoding="utf-8")
        with self.assertRaises(ProjectError):
            load_state(root)

    def test_save_state_validates(self) -> None:
        create_project("保存项目", base=self.base)
        root = self.base / "保存项目"
        state = load_state(root)
        state["stage"] = "99"
        with self.assertRaises(ProjectError):
            save_state(root, state)

    def test_build_state_is_valid(self) -> None:
        state = build_state("构造项目", entry="B")
        self.assertEqual(validate_state(state), [])
        self.assertEqual(state["project"], "构造项目")
        self.assertEqual(validate(state, schema_name="state.schema.json"), [])

    def test_status_card_refreshed_with_stage(self) -> None:
        create_project("状态卡项目", base=self.base)
        root = self.base / "状态卡项目"
        state = load_state(root)
        state["stage"] = "04"
        save_state(root, state)
        refresh_status_card(root)
        card = (root / "状态卡.md").read_text(encoding="utf-8")
        self.assertIn("04", card)
        self.assertIn("当前阶段", card)

    def test_state_path(self) -> None:
        self.assertEqual(
            state_path(self.base / "x"), self.base / "x" / "00_project" / "state.json"
        )

    def test_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as docs, tempfile.TemporaryDirectory() as home:
            env = {
                "AI_FILM_DOCUMENTS_DIR": docs,
                "AI_FILM_PROJECTS_ROOT": str(Path(docs) / "projects"),
                "AI_FILM_WORKBENCH_HOME": home,
            }
            with mock.patch.dict("os.environ", env, clear=False):
                self.assertEqual(detect_documents_dir(), Path(docs))
                self.assertEqual(default_projects_root(), Path(docs) / "projects")
                self.assertEqual(workbench_home(), Path(home))

    def test_schema_file_is_loadable(self) -> None:
        schema = load_schema("state.schema.json")
        self.assertEqual(schema["title"], "Project State v2")

    def test_export_and_restore_roundtrip(self) -> None:
        create_project("导出项目", base=self.base)
        root = self.base / "导出项目"
        (root / "01_story" / "synopsis.md").write_text("# 梗概\n", encoding="utf-8")
        archive = Path(self.tmp.name) / "export.zip"
        report = export_project(root, archive)
        self.assertTrue(archive.is_file())
        self.assertGreater(report["files"], 0)
        restored = restore_project(archive, Path(self.tmp.name) / "restored")
        target = Path(restored["path"])
        self.assertEqual("导出项目", restored["project"])
        self.assertEqual(
            (root / "01_story" / "synopsis.md").read_text(encoding="utf-8"),
            (target / "01_story" / "synopsis.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(load_state(target)["stage"], "01")

    def test_restore_refuses_non_empty_destination(self) -> None:
        create_project("导出项目2", base=self.base)
        root = self.base / "导出项目2"
        archive = Path(self.tmp.name) / "export2.zip"
        export_project(root, archive)
        dest = Path(self.tmp.name) / "restored2"
        (dest / "导出项目2").mkdir(parents=True)
        (dest / "导出项目2" / "x.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ProjectError):
            restore_project(archive, dest)

    def test_restore_rejects_path_traversal(self) -> None:
        archive = Path(self.tmp.name) / "evil.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("../evil.txt", "x")
            handle.writestr("export-metadata.json", json.dumps({"project": "evil"}))
        with self.assertRaises(ProjectError):
            restore_project(archive, Path(self.tmp.name) / "out")


if __name__ == "__main__":
    unittest.main()
