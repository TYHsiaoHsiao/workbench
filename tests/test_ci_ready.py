"""远端 CI 就绪检查测试（M26）：工作流矩阵/步骤与 git remote 检测。"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ci_ready  # noqa: E402

WORKFLOW_TEXT = """name: ci

on:
  push:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    steps:
      - run: python scripts/ci_ready.py --require-remote
      - run: python scripts/run_ci.py
      - run: python scripts/build_release.py
      - run: python scripts/package_smoke.py
      - uses: actions/upload-artifact@v4
"""


class CiReadyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_ciready_")
        self.root = Path(self._tmp)
        workflow_dir = self.root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        self.path = workflow_dir / "ci.yml"
        self.path.write_text(WORKFLOW_TEXT, encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_valid_workflow_passes_without_remote(self) -> None:
        with unittest.mock.patch.object(ci_ready, "list_remotes", return_value=[]):
            report = ci_ready.check(self.root)
        self.assertTrue(report["ok"])
        self.assertFalse(report["remote_configured"])
        self.assertTrue(report["hints"])

    def test_require_remote_blocks_without_remote(self) -> None:
        with unittest.mock.patch.object(ci_ready, "list_remotes", return_value=[]):
            report = ci_ready.check(self.root, require_remote=True)
        self.assertFalse(report["ok"])
        self.assertEqual("未配置 git remote", report["blocked_reason"])

    def test_remote_configured_passes(self) -> None:
        with unittest.mock.patch.object(ci_ready, "list_remotes", return_value=["origin"]):
            report = ci_ready.check(self.root, require_remote=True)
        self.assertTrue(report["ok"])
        self.assertEqual(["origin"], report["remotes"])

    def test_missing_workflow_detected(self) -> None:
        self.path.unlink()
        report = ci_ready.check_workflow(self.root)
        self.assertFalse(report["ok"])
        self.assertIn("工作流文件不存在", report["missing"])

    def test_missing_matrix_phrase_detected(self) -> None:
        self.path.write_text(WORKFLOW_TEXT.replace("windows-latest", "linux-latest"), encoding="utf-8")
        report = ci_ready.check_workflow(self.root)
        self.assertFalse(report["ok"])
        self.assertIn("windows-latest", report["missing"])

    def test_workflow_without_macos_still_passes(self) -> None:
        report = ci_ready.check_workflow(self.root)
        self.assertTrue(report["ok"])
        self.assertFalse(report["macos_present"])

    def test_main_exit_codes(self) -> None:
        with unittest.mock.patch.object(ci_ready, "list_remotes", return_value=[]):
            self.assertEqual(0, ci_ready.main(["--root", str(self.root)]))
            self.assertEqual(1, ci_ready.main(["--root", str(self.root), "--require-remote"]))
        self.path.unlink()
        self.assertEqual(1, ci_ready.main(["--root", str(self.root)]))

    def test_list_remotes_parses_git_output(self) -> None:
        fake = unittest.mock.Mock(returncode=0, stdout="origin\nupstream\n")
        with unittest.mock.patch("subprocess.run", return_value=fake):
            self.assertEqual(["origin", "upstream"], ci_ready.list_remotes(self.root))

    def test_list_remotes_failure_returns_empty(self) -> None:
        fake = unittest.mock.Mock(returncode=128, stdout="")
        with unittest.mock.patch("subprocess.run", return_value=fake):
            self.assertEqual([], ci_ready.list_remotes(self.root))


if __name__ == "__main__":
    unittest.main()
