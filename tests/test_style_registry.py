"""风格注册表：构建脚本（合成风格包）与加载/解析测试。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_style_registry import build_registry  # noqa: E402
from contracts import validate  # noqa: E402
from style_service import StyleRegistry, StyleRegistryError, load_style_registry  # noqa: E402

COLORS = ["#1A1A2E", "#E94560", "#16213E", "#0F3460", "#533483", "#F5F5F5"]
RATIOS = [20, 20, 20, 15, 15, 10]


def write_palette(director_dir: Path, name_en: str = "Test Director", with_style_profile: bool = True) -> None:
    palette_dir = director_dir / "assets" / "color_palettes"
    palette_dir.mkdir(parents=True)
    primary = [
        {"code": f"P{index + 1}", "hex": hex_value, "name_zh": f"主色{index + 1}",
         "name_en": f"Primary {index + 1}", "ratio": ratio / 100.0, "rgb": [0, 0, 0], "hsl": [0, 0, 0]}
        for index, (hex_value, ratio) in enumerate(zip(COLORS, RATIOS))
    ]
    emotional = [
        {"code": f"E{index + 1}", "hex": "#223344", "name_zh": f"情绪{index + 1}",
         "name_en": f"Emotion {index + 1}", "emotion": "压抑", "rgb": [0, 0, 0], "hsl": [0, 0, 0]}
        for index in range(4)
    ]
    data = {
        "director": {"id": director_dir.name[:3], "name_en": name_en, "name_zh": "测试导演",
                     "category": "测试", "nationality": "中国", "active_years": "1990-2020", "era": "现代"},
        "palette": {"primary": primary, "emotional": emotional},
        "lighting": {"key_light": "侧逆光", "highlight_tint": "青", "shadow_tint": "蓝",
                     "contrast_ratio": "高", "overall_tone": "冷"},
        "composition_keywords": ["对称构图", "框中框"],
        "color_keywords": ["冷蓝", "霓虹红"],
        "mood_keywords": ["压抑", "孤独"],
    }
    if with_style_profile:
        data["style_profile"] = {
            "definition": "冷蓝色调悬疑风格",
            "lighting": "侧逆光与低照度",
            "framing": "对称构图与框中框",
            "grading": "青蓝阴影、红色点缀",
            "avoid": "与参考作品完全一致的构图；水印与文字叠加",
        }
    (palette_dir / "palette.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (palette_dir / "palette_main.png").write_bytes(b"fake")


def make_director(
    category_dir: Path,
    dirname: str,
    prompt_count: int = 4,
    broken_link: bool = False,
    with_references: bool = True,
    old_absolute_path: bool = False,
) -> Path:
    director = category_dir / dirname
    director.mkdir(parents=True)
    write_palette(director)
    prompts_dir = director / "prompts"
    prompts_dir.mkdir()
    for index, filename in enumerate(
        ["midjourney_prompts.md", "conversational_prompts.md", "video_prompts.md", "stable_diffusion_prompts.md"]
    ):
        if index < prompt_count:
            (prompts_dir / filename).write_text("# 提示词\n\n第一段\n第二段\n", encoding="utf-8")
    card = ["# 色卡主文档", "", "## 色彩"]
    card.append("版权说明：仅供学习。")
    if broken_link:
        card.append("![示意图](missing.png)")
    (director / "色卡主文档.md").write_text("\n".join(card) + "\n", encoding="utf-8")
    if with_references:
        refs = director / "assets" / "references"
        refs.mkdir(parents=True)
        (refs / "reference_sources.md").write_text("来源说明：合成测试数据。\n", encoding="utf-8")
        if old_absolute_path:
            (refs / "reference_director_manifest.json").write_text(
                json.dumps({"frames": [r"D:\legacy\path\frame.jpg"]}, ensure_ascii=False),
                encoding="utf-8",
            )
    return director


class StyleRegistryBuildTest(unittest.TestCase):
    def _make_pack(self, root: Path) -> None:
        category = root / "01_测试类型"
        category.mkdir(parents=True)
        make_director(category, "001_TestDirector_测试导演")
        make_director(category, "002_Broken Pack", prompt_count=2, broken_link=True,
                      with_references=True, old_absolute_path=True)
        make_director(category, "003_NoPalette", prompt_count=0, with_references=False)
        # 003 去掉 palette，强制 C 级
        (category / "003_NoPalette" / "assets" / "color_palettes" / "palette.json").unlink()

    def test_build_registry_levels_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            self._make_pack(root)
            registry = build_registry(root)
            errors = validate(registry, schema_name="style-registry.schema.json")
            self.assertEqual([], errors, msg=errors)
            self.assertEqual([1, 1, 1], [
                registry["qc"]["grade_counts"]["A"],
                registry["qc"]["grade_counts"]["B"],
                registry["qc"]["grade_counts"]["C"],
            ])
            self.assertEqual(3, registry["source"]["directors"])
            self.assertEqual(1, len(registry["categories"]))
            self.assertEqual(3, registry["categories"][0]["count"])
            entries = {entry["id"]: entry for entry in registry["entries"]}
            self.assertEqual("A", entries["001"]["quality"])
            self.assertEqual("B", entries["002"]["quality"])
            self.assertEqual("C", entries["003"]["quality"])
            self.assertIn("broken_image_links_1", entries["002"]["issues"])
            self.assertIn("dir_name_space", entries["002"]["issues"])
            self.assertIn("manifest_old_absolute_path", entries["002"]["issues"])
            self.assertIn("missing_references", entries["003"]["issues"])
            self.assertIn("missing_palette_json", entries["003"]["issues"])
            self.assertEqual(6, len(entries["001"]["palette"]["primary"]))
            self.assertEqual(4, len(entries["001"]["prompts"]))

    def test_load_and_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            self._make_pack(root)
            registry_path = Path(tmp) / "style-registry.json"
            registry_path.write_text(
                json.dumps(build_registry(root), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            registry = load_style_registry(registry_path)
            self.assertEqual(3, len(registry))
            self.assertEqual("001", registry.get("001")["id"])
            self.assertEqual("001", registry.get("1")["id"])
            self.assertEqual("001", registry.get("TestDirector")["id"])
            self.assertEqual("001", registry.get("测试导演")["id"])
            self.assertEqual("001", registry.get("01_测试类型/001_TestDirector_测试导演")["id"])
            with self.assertRaises(StyleRegistryError):
                registry.get("不存在的导演")
            summary = registry.summary()
            self.assertEqual(3, summary["directors"])
            listed = registry.list_entries(quality="B")
            self.assertEqual(["002"], [item["id"] for item in listed])

    def test_ambiguous_name_raises(self) -> None:
        data = {
            "contract_version": "1.0",
            "generated_at": "2026-01-01T00:00:00+08:00",
            "source": {"root_name": "pack", "directors": 2, "categories": 1},
            "categories": [{"id": "01", "name": "测试", "directory": "01_测试", "count": 2}],
            "entries": [
                {"id": "001", "name_en": "Same", "name_zh": "同名", "directory": "01_测试/001_A",
                 "category": "01", "quality": "B", "issues": [], "flags": {}},
                {"id": "002", "name_en": "Same", "name_zh": "同名", "directory": "01_测试/002_B",
                 "category": "01", "quality": "B", "issues": [], "flags": {}},
            ],
            "qc": {"grade_counts": {"A": 0, "B": 2, "C": 0}, "issue_counts": {},
                   "duplicate_palettes": 0, "duplicate_palette_groups": 0},
        }
        registry = StyleRegistry(data, Path("memory.json"))
        with self.assertRaises(StyleRegistryError) as ctx:
            registry.get("Same")
        self.assertIn("多个条目", str(ctx.exception))

    def test_bad_registry_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"contract_version": "1.0"}', encoding="utf-8")
            with self.assertRaises(StyleRegistryError):
                load_style_registry(path)


if __name__ == "__main__":
    unittest.main()
