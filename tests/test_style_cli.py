"""风格服务 CLI：list / show / resolve / validate / apply / inject。"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main  # noqa: E402
from core_router.project import create_project  # noqa: E402

MJ_BODY = "主体：雨夜旧城街道；风格：冷调悬疑电影感；光线：侧逆光；构图：对称构图 --ar 16:9"


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class StyleCliTest(unittest.TestCase):
    def test_list_json(self) -> None:
        code, output = run_cli(["style", "list", "--json"])
        self.assertEqual(0, code, msg=output)
        payload = json.loads(output)
        self.assertEqual(200, payload["count"])
        self.assertEqual(200, len(payload["entries"]))

    def test_list_quality_filter(self) -> None:
        code, output = run_cli(["style", "list", "--quality", "A"])
        self.assertEqual(0, code, msg=output)
        self.assertIn("共 140 条", output)

    def test_show_and_resolve(self) -> None:
        code, output = run_cli(["style", "show", "001", "--json"])
        self.assertEqual(0, code, msg=output)
        profile = json.loads(output)
        self.assertEqual("001", profile["director_no"])
        self.assertEqual(6, len(profile["palette"]))
        code, output = run_cli(["style", "resolve", "001", "--json"])
        self.assertEqual(0, code, msg=output)
        entry = json.loads(output)
        self.assertEqual("001", entry["id"])
        self.assertEqual(4, len(entry["prompts"]))
        code, output = run_cli(["style", "show", "不存在的导演"])
        self.assertEqual(1, code, msg=output)

    def test_validate(self) -> None:
        code, output = run_cli(["style", "validate", "--tool", "mj", "--text", MJ_BODY])
        self.assertEqual(0, code, msg=output)
        self.assertIn("结构校验通过", output)
        code, output = run_cli(["style", "validate", "--tool", "mj", "--text", "一个画面"])
        self.assertEqual(1, code, msg=output)
        code, output = run_cli(["style", "validate", "--tool", "未知模型", "--text", "x"])
        self.assertEqual(1, code, msg=output)

    def test_apply_and_inject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = Path(create_project("CLI风格项目", base=base / "projects")["path"])
            prompt_file = base / "prompt.md"
            prompt_file.write_text(MJ_BODY, encoding="utf-8")
            code, output = run_cli(["style", "apply", "001", "--project", str(project), "--tool", "mj"])
            self.assertEqual(0, code, msg=output)
            self.assertTrue((project / "00_project/style-cards/style-001-mj-profile.json").is_file())
            code, output = run_cli([
                "style", "inject", "001", "--project", str(project),
                "--stage", "06", "--tool", "mj", "--prompt-file", str(prompt_file), "--json",
            ])
            self.assertEqual(0, code, msg=output)
            report = json.loads(output)
            self.assertTrue(Path(report["record"]).is_file())
            self.assertIn("【风格卡】", report["combined_prompt"])
            cards = list((project / "00_project/style-cards").glob("*injection*"))
            self.assertEqual(1, len(cards))


if __name__ == "__main__":
    unittest.main()
