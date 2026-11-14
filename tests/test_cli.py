"""CLI 冒烟测试：版本、自检、校验、品牌守卫、参数错误。"""
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
from core_router.state import default_state  # noqa: E402


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class CliTest(unittest.TestCase):
    def test_version(self) -> None:
        code, output = run_cli(["version"])
        self.assertEqual(0, code)
        self.assertIn("workbench", output)
        self.assertIn("contracts v1.0", output)

    def test_doctor_passes(self) -> None:
        code, output = run_cli(["doctor"])
        self.assertEqual(0, code, msg=output)
        self.assertNotIn("[FAIL]", output)

    def test_brand_guard_json_clean(self) -> None:
        code, output = run_cli(["brand-guard", "--json"])
        self.assertEqual(0, code, msg=output)
        report = json.loads(output)
        self.assertTrue(report["ok"])

    def test_check_registry(self) -> None:
        code, output = run_cli(["check"])
        self.assertEqual(0, code, msg=output)
        self.assertIn("校验通过", output)

    def test_validate_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps(default_state("校验项目"), ensure_ascii=False),
                            encoding="utf-8")
            code, output = run_cli(["validate", str(path), "--schema", "state.schema.json"])
            self.assertEqual(0, code, msg=output)
            broken = default_state("校验项目")
            broken["stage"] = "09"
            path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
            code, output = run_cli(["validate", str(path), "--schema", "state.schema.json"])
            self.assertEqual(1, code)
            self.assertIn("$.stage", output)

    def test_init_empty_name_is_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli(["init", "   ", "--project-root", tmp])
            self.assertEqual(2, code)
            self.assertIn("不能为空", output)

    def test_reference_list_after_init(self) -> None:
        from core_router.project import create_project

        with tempfile.TemporaryDirectory() as tmp:
            create_project("参考项目", base=Path(tmp))
            project = Path(tmp) / "参考项目"
            code, output = run_cli(
                ["reference", "list", "--project", str(project), "--stage", "05", "--json"]
            )
            self.assertEqual(0, code, msg=output)
            payload = json.loads(output)
            self.assertEqual(0, payload["count"])
            self.assertEqual("05", payload["stage"])

    def test_unknown_command_exits_with_usage_code(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(["not-a-command"])
        self.assertEqual(2, ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
