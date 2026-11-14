"""风格适配器：工具别名、v1 结构校验、风格块与组合提示词。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from style_service import (  # noqa: E402
    TOOL_IDS,
    AdapterError,
    combined_prompt,
    normalize_tool,
    stage_tools,
    style_block,
    validate_prompt,
)
from style_service.service import build_profile  # noqa: E402

COLORS = ["#1A1A2E", "#E94560", "#16213E", "#0F3460", "#533483", "#F5F5F5"]


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


class AdapterTest(unittest.TestCase):
    def test_normalize_tool_aliases(self) -> None:
        self.assertEqual("mj", normalize_tool("Midjourney"))
        self.assertEqual("banana", normalize_tool("gpt-image"))
        self.assertEqual("seedance_2_0", normalize_tool("Seedance 2.0"))
        self.assertEqual("seedance_2_5", normalize_tool("seedance2.5"))
        self.assertEqual("h3", normalize_tool("MiniMax H3"))
        self.assertEqual("sd", normalize_tool("stable_diffusion"))
        for tool in TOOL_IDS:
            self.assertEqual(tool, normalize_tool(tool))
        with self.assertRaises(AdapterError):
            normalize_tool("未知模型")

    def test_stage_tools(self) -> None:
        self.assertEqual(("mj", "banana", "sd"), stage_tools("06"))
        self.assertIn("h3", stage_tools("08"))
        with self.assertRaises(AdapterError):
            stage_tools("05")

    def test_valid_prompts_pass(self) -> None:
        mj = "主体：旧城街道；风格：冷调悬疑；光线：侧逆光；构图：对称构图 --ar 16:9"
        self.assertEqual([], validate_prompt("mj", mj))
        banana = "主体：人物；风格：写实电影感；光线：柔光"
        self.assertEqual([], validate_prompt("banana", banana))
        h3 = "画面：雨夜街道；镜头：缓慢推近；声音：雨声；overall_soundscape：雨声与脚步"
        self.assertEqual([], validate_prompt("h3", h3))
        sd = "Positive: cinematic portrait\nNegative: blur, text"
        self.assertEqual([], validate_prompt("sd", sd))

    def test_invalid_prompts_reported(self) -> None:
        self.assertIn("--ar", " ".join(validate_prompt("mj", "主体：人物；风格：写实；光线：柔光；构图：居中")))
        self.assertTrue(any("否定式" in issue for issue in validate_prompt("banana", "主体：人物；风格：写实；光线：柔光；不要出现文字")))
        self.assertTrue(any("连续性" in issue for issue in validate_prompt("seedance_2_0", "主体：人物；动作：走；场景：街；镜头：推近；光线：夜；上一镜头继续")))
        self.assertTrue(any("时长" in issue for issue in validate_prompt("seedance_2_0", "主体：人物；动作：走；场景：街；镜头：推近；光线：夜；20秒")))
        self.assertTrue(any("运镜" in issue for issue in validate_prompt("runway", "主体：人物；镜头：推近并环绕")))
        self.assertTrue(any("运镜" in issue for issue in validate_prompt("runway", "主体：人物；镜头：固定")))
        self.assertEqual(["提示词为空"], validate_prompt("mj", "   "))

    def test_style_block_and_combined(self) -> None:
        profile = build_profile(make_entry())
        block = style_block(profile)
        self.assertIn("【风格卡】", block)
        self.assertIn("测试导演", block)
        self.assertIn(COLORS[0], block)
        self.assertIn("侧逆光", block)
        combined = combined_prompt(profile, "mj", "主体：人物；风格：写实；光线：柔光；构图：居中 --ar 1:1")
        self.assertTrue(combined.startswith("【风格卡】"))
        self.assertIn("--ar 1:1", combined)
        mj_adapter = style_block(profile, "mj")
        self.assertIn("本工具适配", mj_adapter)


if __name__ == "__main__":
    unittest.main()
