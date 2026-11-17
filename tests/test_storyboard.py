# -*- coding: utf-8 -*-
"""storyboard 包测试：故事 → 分镜 / 提示词 / 字幕 / 配音 / 多风格对比。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

import storyboard  # noqa: E402
from storyboard import StoryboardError, DEMO_STORY  # noqa: E402


class StoryboardGenerateTest(unittest.TestCase):
    def test_generate_demo(self):
        data = storyboard.generate(DEMO_STORY)
        self.assertEqual(data["title"], "午夜来电")
        self.assertEqual(data["style_name"], "悬疑")
        self.assertGreaterEqual(len(data["shots"]), 6)
        self.assertEqual(data["character"], "店员")
        self.assertEqual(data["compare"], [])

    def test_generate_rejects_invalid_inputs(self):
        with self.assertRaises(StoryboardError):
            storyboard.generate("   ")
        with self.assertRaises(StoryboardError):
            storyboard.generate("雨夜，一个人走在路上。", aspect="4:3")
        with self.assertRaises(StoryboardError):
            storyboard.generate("雨夜，一个人走在路上。", duration=1000)
        with self.assertRaises(StoryboardError):
            storyboard.generate("雨夜，一个人走在路上。", duration="abc")

    def test_generate_normalizes_style_and_compare(self):
        data = storyboard.generate(DEMO_STORY, style="不存在的风格", compare="悬疑,写实,乱写")
        self.assertEqual(data["style_name"], "悬疑")
        self.assertEqual(data["compare"], ["悬疑", "写实"])


class StoryboardPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "sb-test-001"
        self.data = storyboard.generate(DEMO_STORY, compare="悬疑,写实")

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_package_files(self):
        meta = storyboard.write_package(self.out, self.data)
        names = {item["name"] for item in meta["files"]}
        expected = {
            "分镜表.md", "提示词包.md", "prompts.txt", "分镜与提示词.html",
            "即梦提示词.txt", "可灵提示词.txt", "Seedance提示词.txt", "平台-负面词.txt",
            "字幕.srt", "配音清单.md", "多风格对比.md", "多风格对比.html", "meta.json",
        }
        self.assertEqual(names, expected)
        self.assertTrue(all((self.out / name).stat().st_size > 0 for name in expected))
        self.assertEqual(meta["shots"], len(self.data["shots"]))
        self.assertEqual(len(meta["shot_preview"]), meta["shots"])
        self.assertEqual(meta["compare"], ["悬疑", "写实"])
        self.assertEqual(meta["run_id"], self.out.name)

    def test_srt_blocks_match_shots(self):
        storyboard.write_package(self.out, self.data)
        srt = (self.out / "字幕.srt").read_text(encoding="utf-8").strip()
        blocks = [b for b in srt.split("\n\n") if b.strip()]
        self.assertEqual(len(blocks), len(self.data["shots"]))
        self.assertIn("00:00:00,000 -->", srt)

    def test_platform_files_line_count(self):
        storyboard.write_package(self.out, self.data)
        shots = len(self.data["shots"])
        for name in storyboard.PLATFORM_FILES:
            lines = [ln for ln in (self.out / name).read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), shots, name)

    def test_compare_html_contains_all_styles(self):
        storyboard.write_package(self.out, self.data)
        page = (self.out / storyboard.COMPARE_HTML).read_text(encoding="utf-8")
        self.assertIn("多风格对比", page)
        self.assertIn("悬疑", page)
        self.assertIn("写实", page)
        self.assertNotIn("都市", page)


if __name__ == "__main__":
    unittest.main()
