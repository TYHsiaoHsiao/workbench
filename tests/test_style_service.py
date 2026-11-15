"""风格服务：风格卡生成、项目挂载、06/08 注入与默认不注入。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from contracts import validate  # noqa: E402
from core_router.project import create_project, load_state  # noqa: E402
from style_service import (  # noqa: E402
    StyleRegistry,
    StyleService,
    StyleServiceError,
)

COLORS = ["#1A1A2E", "#E94560", "#16213E", "#0F3460", "#533483", "#F5F5F5"]

MJ_BODY = "主体：雨夜旧城街道；风格：冷调悬疑电影感；光线：侧逆光；构图：对称构图 --ar 16:9"

SEEDANCE_BODY = (
    "【整体】冷峻悬疑短片，节奏克制。"
    "【光影】无影灯冷白，监护仪绿光。"
    "【镜头】固定机位缓慢推近。"
    "【声音】只有监护仪滴答声。"
    "【对白】无。"
)


def make_entry() -> dict:
    return {
        "id": "001",
        "name_en": "TestDirector",
        "name_zh": "测试导演",
        "directory": "01_测试类型/001_TestDirector_测试导演",
        "category": "01",
        "category_name": "测试类型",
        "nationality": "中国",
        "palette": {
            "primary": [
                {"code": f"P{index + 1}", "hex": value, "name_zh": f"主色{index + 1}",
                 "ratio": ratio}
                for index, (value, ratio) in enumerate(zip(COLORS, [20, 20, 20, 15, 15, 10]))
            ],
            "emotional": [
                {"code": f"E{index + 1}", "hex": "#223344", "name_zh": f"情绪{index + 1}",
                 "emotion": "压抑"} for index in range(4)
            ],
            "primary_ratio_sum": 100,
        },
        "style_profile": {
            "definition": "冷蓝色调悬疑风格",
            "lighting": "侧逆光与低照度",
            "framing": "对称构图",
            "grading": "青蓝阴影",
            "avoid": "与参考作品完全一致的构图；水印与文字叠加",
        },
        "keywords": {"composition": ["对称构图"], "color": ["冷蓝"], "mood": ["压抑"]},
        "prompts": {"midjourney": 100, "conversational": 100, "video": 100, "stable_diffusion": 100},
        "references_count": 2,
        "quality": "A",
        "issues": [],
        "flags": {
            "has_palette_json": True, "has_color_card": True, "has_prompt_files": True,
            "has_references": True, "has_copyright_note": True, "broken_image_links": 0,
        },
    }


def make_registry() -> StyleRegistry:
    data = {
        "contract_version": "1.0",
        "generated_at": "2026-01-01T00:00:00+08:00",
        "source": {"root_name": "pack", "directors": 1, "categories": 1},
        "categories": [{"id": "01", "name": "测试类型", "directory": "01_测试类型", "count": 1}],
        "entries": [make_entry()],
        "qc": {"grade_counts": {"A": 1, "B": 0, "C": 0}, "issue_counts": {},
               "duplicate_palettes": 0, "duplicate_palette_groups": 0},
    }
    return StyleRegistry(data, Path("memory-registry.json"))


class StyleServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("风格测试项目", base=self.base / "projects")
        self.project = Path(report["path"])
        self.service = StyleService(registry=make_registry())

    def test_build_profile_matches_contract(self) -> None:
        profile = self.service.build("001")
        self.assertEqual([], validate(profile, schema_name="style-profile.schema.json"))
        self.assertEqual("001", profile["director_no"])
        self.assertEqual(6, len(profile["palette"]))
        self.assertEqual(8, len(profile["tool_adapters"]))
        self.assertEqual(100, sum(item["ratio"] for item in profile["palette"]))
        self.assertEqual("A", profile["quality"])

    def test_apply_writes_card_and_state(self) -> None:
        report = self.service.apply(self.project, "001")
        card = Path(report["card"])
        self.assertTrue(card.is_file())
        self.assertEqual("00_project/style-cards/style-001-profile.json",
                         card.relative_to(self.project).as_posix())
        state = load_state(self.project)
        self.assertEqual("on", state["style"]["status"])
        self.assertEqual("00_project/style-cards/style-001-profile.json",
                         state["style"]["profile_path"])
        on_disk = json.loads(card.read_text(encoding="utf-8"))
        self.assertEqual([], validate(on_disk, schema_name="style-profile.schema.json"))

    def test_apply_with_tool(self) -> None:
        report = self.service.apply(self.project, "001", tool="mj")
        self.assertTrue(report["card"].endswith("style-001-mj-profile.json"))
        self.assertTrue(report["profile"]["profile_id"].endswith("-mj"))

    def test_inject_writes_record(self) -> None:
        self.service.apply(self.project, "001")
        report = self.service.inject(self.project, "001", "06", "mj", MJ_BODY)
        self.assertTrue(Path(report["record"]).is_file())
        self.assertTrue(report["combined_prompt"].startswith("【风格卡】"))
        self.assertIn("对称构图", report["combined_prompt"])
        record = json.loads(Path(report["record"]).read_text(encoding="utf-8"))
        self.assertEqual("06", record["stage"])
        self.assertEqual("mj", record["tool"])
        self.assertEqual([], record["issues"])
        self.assertEqual(64, len(record["prompt_sha256"]))
        self.assertEqual(report["record_sha256"], record["prompt_sha256"])

    def test_default_no_injection(self) -> None:
        self.service.apply(self.project, "001")
        cards = list((self.project / "00_project" / "style-cards").glob("*injection*"))
        self.assertEqual([], cards)

    def test_inject_requires_applied_style(self) -> None:
        with self.assertRaises(StyleServiceError):
            self.service.inject(self.project, "001", "06", "mj", MJ_BODY)

    def test_inject_structure_failure(self) -> None:
        self.service.apply(self.project, "001")
        with self.assertRaises(StyleServiceError) as ctx:
            self.service.inject(self.project, "001", "06", "mj", "主体：一个人")
        self.assertIn("结构校验", str(ctx.exception))

    def test_inject_stage_tool_mismatch(self) -> None:
        self.service.apply(self.project, "001")
        with self.assertRaises(StyleServiceError):
            self.service.inject(self.project, "001", "06", "h3",
                                "画面：雨；镜头：推近；声音：雨声；overall_soundscape：雨")

    def test_unknown_ref_raises(self) -> None:
        with self.assertRaises(StyleServiceError):
            self.service.get("999")

    def test_inject_batch_writes_single_record(self) -> None:
        self.service.apply(self.project, "001")
        items = [
            {"shot": "SH-01", "prompt": SEEDANCE_BODY},
            {"shot": "SH-02", "prompt": SEEDANCE_BODY},
        ]
        report = self.service.inject_batch(self.project, "08", "seedance_2_5", items)
        self.assertEqual(2, report["count"])
        record_path = Path(report["record"])
        self.assertTrue(record_path.is_file())
        self.assertTrue(record_path.name.endswith("-batch.json"))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(2, len(record["items"]))
        self.assertEqual(64, len(record["items"][0]["prompt_sha256"]))
        state = load_state(self.project)
        self.assertIn("批量注入", state["style"]["note"])

    def test_inject_batch_per_shot_records(self) -> None:
        self.service.apply(self.project, "001")
        items = [
            {"shot": "SH-01", "prompt": SEEDANCE_BODY},
            {"shot": "SH-02", "prompt": SEEDANCE_BODY},
        ]
        report = self.service.inject_batch(
            self.project, "08", "seedance_2_5", items, per_shot_records=True
        )
        self.assertEqual(2, len(report["shot_records"]))
        for path, shot in zip(report["shot_records"], ("SH-01", "SH-02")):
            record = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(shot, record["shot"])
            self.assertEqual(64, len(record["prompt_sha256"]))
            self.assertTrue(Path(path).name.endswith(f"{shot}.json"))
        batch = json.loads(Path(report["record"]).read_text(encoding="utf-8"))
        self.assertEqual(2, len(batch["items"]))

    def test_inject_batch_rejects_bad_item(self) -> None:
        self.service.apply(self.project, "001")
        with self.assertRaises(StyleServiceError) as ctx:
            self.service.inject_batch(self.project, "08", "seedance_2_5",
                                      [{"shot": "SH-01", "prompt": "只有一句话"}])
        self.assertIn("批量注入结构校验", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
