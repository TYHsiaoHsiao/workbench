"""init 测试：目录骨架、状态契约、幂等与覆盖。"""
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

from brand_guard import load_wordlist  # noqa: E402
from cli.main import PROJECT_DIRS, main  # noqa: E402
from core_router.state import validate_state  # noqa: E402

TERMS = load_wordlist(REPO_ROOT / "packages" / "brand_guard" / "wordlist.b64")


def run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class InitTest(unittest.TestCase):
    def _init(self, root: str, name: str = "测试项目", entry: str = "B") -> tuple[int, str]:
        return run_cli(["init", name, "--project-root", root, "--entry", entry, "--json"])

    def test_project_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self._init(tmp)
            self.assertEqual(0, code, msg=output)
            payload = json.loads(output)
            self.assertTrue(payload["ok"])
            project = Path(payload["path"])
            self.assertEqual("01", payload["stage"])
            for rel in PROJECT_DIRS:
                self.assertTrue((project / rel).is_dir(), msg=rel)
            self.assertTrue((project / "AGENTS.md").is_file())
            self.assertTrue((project / "状态卡.md").is_file())
            self.assertTrue((project / "00_project" / "reference-memory.md").is_file())
            self.assertTrue((project / "00_project" / "brief.md").is_file())

            state = json.loads((project / "00_project" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual([], validate_state(state))
            self.assertEqual("测试项目", state["project"])
            self.assertEqual("B", state["entry"])
            self.assertEqual("01", state["stage"])

    def test_generated_files_have_no_forbidden_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self._init(tmp)
            self.assertEqual(0, code, msg=output)
            project = Path(json.loads(output)["path"])
            for path in project.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for term in TERMS:
                    self.assertNotIn(term, text, msg=str(path))

    def test_reference_memory_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self._init(tmp)
            self.assertEqual(0, code, msg=output)
            project = Path(json.loads(output)["path"])
            memory = (project / "00_project" / "reference-memory.md").read_text(encoding="utf-8")
            self.assertIn("参考方法001", memory)
            self.assertIn("知识库外挂状态：未调用", memory)

    def test_existing_project_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self._init(tmp)
            self.assertEqual(0, code, msg=output)
            code, output = self._init(tmp)
            self.assertEqual(1, code)
            self.assertIn("--force", output)
            code, output = run_cli(["init", "测试项目", "--project-root", tmp, "--force"])
            self.assertEqual(0, code, msg=output)

    def test_entry_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_cli(["init", "入口项目", "--project-root", tmp,
                                    "--entry", "D", "--mode", "stage"])
            self.assertEqual(0, code, msg=output)
            project = Path(tmp) / "入口项目"
            state = json.loads((project / "00_project" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual("D", state["entry"])
            self.assertEqual("stage", state["mode"])


if __name__ == "__main__":
    unittest.main()
