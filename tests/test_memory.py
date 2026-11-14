"""跨阶段参考记忆测试：契约加载、阶段筛选、状态过滤、坏数据。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.memory import (  # noqa: E402
    MemoryError,
    entries_for_stage,
    load_memory,
    scope_for_stage,
    summarize,
)
from core_router.project import REFERENCE_MEMORY_JSON, create_project  # noqa: E402


def entry(method_id: str, scope: list[str], status: str = "enabled") -> dict:
    return {
        "id": method_id,
        "status": status,
        "source": "测试来源",
        "type": "method_book",
        "local_path": "08-编剧方法书籍/示例.md",
        "page_hits": "第 3 页 / 命中「悬念」",
        "method": "示例方法",
        "scope": scope,
        "stage": "05",
        "binding_facts": [],
        "forbidden": [],
        "confirmed": {"by": "测试", "at": "2026-11-14T00:00:00"},
        "change_log": [{"at": "2026-11-14T00:00:00", "action": "created", "note": "测试"}],
    }


class MemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "projects"
        self.base.mkdir()
        self.root = self.base / "记忆项目"
        create_project("记忆项目", base=self.base)
        self.path = self.root / "00_project" / REFERENCE_MEMORY_JSON

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_memory(self, entries: list[dict]) -> None:
        payload = {"contract_version": "1.0", "entries": entries}
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_empty_memory_loads(self) -> None:
        memory = load_memory(self.root)
        self.assertEqual([], memory["entries"])
        summary = summarize(memory)
        self.assertEqual(0, summary["total"])
        self.assertEqual(0, summary["enabled"])

    def test_stage_scope_mapping(self) -> None:
        self.assertEqual("story_01_05", scope_for_stage("05"))
        self.assertEqual("image_06", scope_for_stage("06"))
        self.assertEqual("camera_08", scope_for_stage("08"))
        with self.assertRaises(MemoryError):
            scope_for_stage("09")

    def test_filters_by_scope_and_status(self) -> None:
        self.write_memory(
            [
                entry("参考方法001", ["story_01_05"]),
                entry("参考方法002", ["story_01_05"], status="disabled"),
                entry("参考方法003", ["image_06"]),
                entry("参考方法004", ["full"]),
            ]
        )
        memory = load_memory(self.root)
        story = entries_for_stage(memory, "05")
        self.assertEqual(["参考方法001", "参考方法004"], [item["id"] for item in story])
        image = entries_for_stage(memory, "06")
        self.assertEqual(["参考方法003", "参考方法004"], [item["id"] for item in image])
        camera = entries_for_stage(memory, "08")
        self.assertEqual(["参考方法004"], [item["id"] for item in camera])
        summary = summarize(memory)
        self.assertEqual(4, summary["total"])
        self.assertEqual(3, summary["enabled"])
        self.assertEqual(1, summary["disabled"])

    def test_invalid_memory_raises(self) -> None:
        self.path.write_text(json.dumps({"contract_version": "1.0", "entries": [{"id": "bad"}]}, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(MemoryError):
            load_memory(self.root)
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(MemoryError):
            load_memory(self.root)


if __name__ == "__main__":
    unittest.main()
