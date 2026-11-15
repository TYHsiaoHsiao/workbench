"""CI 工具脚本测试（M17）：文档链接检查 / 发行包冒烟 / NFR 基准。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bench  # noqa: E402
import check_doc_links  # noqa: E402
import check_fr_mapping  # noqa: E402
import package_smoke  # noqa: E402


class DocLinksTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_doclinks_")
        self.root = Path(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_link_detected(self) -> None:
        self._write("docs/a.md", "[B](b.md)")
        checked, missing = check_doc_links.check(self.root)
        self.assertEqual(1, checked)
        self.assertEqual(1, len(missing))
        self.assertEqual("b.md", missing[0]["target"])
        self.assertEqual("docs/a.md", missing[0]["file"])

    def test_existing_links_ok(self) -> None:
        self._write("docs/b.md", "# B")
        self._write("scripts/x.py", "")
        self._write("README.md", "见 [B](docs/b.md) 与 `scripts/x.py`")
        _, missing = check_doc_links.check(self.root)
        self.assertEqual([], missing)

    def test_skips_urls_fences_and_runtime_paths(self) -> None:
        self._write("README.md", (
            "[x](https://example.com)\n"
            "```bash\n"
            "`missing.md`\n"
            "```\n"
            "`00_project/state.json`\n"
            "`scripts/none.py`"
        ))
        checked, missing = check_doc_links.check(self.root)
        # 只应检查 scripts/none.py 一处，且报告缺失
        self.assertEqual(1, checked)
        self.assertEqual("scripts/none.py", missing[0]["target"])

    def test_main_exit_codes(self) -> None:
        self._write("README.md", "[ok](README.md)")
        self.assertEqual(0, check_doc_links.main(["--root", str(self.root)]))
        self._write("README.md", "[bad](missing.md)")
        self.assertEqual(1, check_doc_links.main(["--root", str(self.root)]))


class PackageSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_pkgtest_")
        self.root = Path(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_zip(self, name: str = "workbench-9.9.9.zip") -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("workbench/VERSION", "9.9.9\n")
            zf.writestr("workbench/workbench.py", "print('demo')\n")
        return path

    def test_find_latest_zip(self) -> None:
        first = self._make_zip("workbench-1.0.0.zip")
        second = self._make_zip("workbench-2.0.0.zip")
        os.utime(first, (1000, 1000))
        os.utime(second, (2000, 2000))
        self.assertEqual(second, package_smoke.find_latest_zip(self.root))

    def test_sha256_match_and_mismatch(self) -> None:
        path = self._make_zip()
        digest = package_smoke.sha256_file(path)
        sums = path.with_suffix(".sha256")
        sums.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
        ok, _ = package_smoke.verify_sha(path)
        self.assertTrue(ok)
        sums.write_text("0" * 64 + f"  {path.name}\n", encoding="utf-8")
        ok, detail = package_smoke.verify_sha(path)
        self.assertFalse(ok)
        self.assertIn("expected", detail)

    def test_missing_checksum_file(self) -> None:
        path = self._make_zip()
        ok, detail = package_smoke.verify_sha(path)
        self.assertFalse(ok)
        self.assertIn("校验文件", detail)

    def test_extract_returns_release_root(self) -> None:
        path = self._make_zip()
        root = package_smoke.extract_zip(path, self.root / "out")
        self.assertTrue((root / "workbench.py").exists())
        self.assertEqual("9.9.9", (root / "VERSION").read_text(encoding="utf-8").strip())


class BenchTest(unittest.TestCase):
    def test_summarize(self) -> None:
        summary = bench.summarize([0.01, 0.02, 0.03])
        self.assertEqual(3, summary["runs"])
        self.assertEqual(10.0, summary["min_ms"])
        self.assertEqual(20.0, summary["median_ms"])
        self.assertEqual(30.0, summary["max_ms"])


class FrMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_frmap_")
        self.root = Path(self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_trace(self, ids: list[str]) -> Path:
        path = self.root / "docs" / "requirements-traceability.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(f"| {fr} 名称 | P0 | 实现 | M1 | 证据 | 已实现 |" for fr in ids)
        path.write_text(f"# 追溯\n\n| FR | 优先级 |\n|---|---|\n{rows}\n", encoding="utf-8")
        return path

    def _write_prd(self, ids: list[str]) -> Path:
        path = self.root / "PRD.md"
        headings = "\n\n".join(f"### {fr} 需求" for fr in ids)
        path.write_text(headings + "\n", encoding="utf-8")
        return path

    def test_complete_mapping_passes(self) -> None:
        self._write_trace(list(check_fr_mapping.EXPECTED_FR))
        report = check_fr_mapping.check(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(22, len(report["found"]))
        self.assertEqual([], report["missing"])

    def test_missing_fr_detected(self) -> None:
        ids = [fr for fr in check_fr_mapping.EXPECTED_FR if fr != "FR-10"]
        self._write_trace(ids)
        report = check_fr_mapping.check(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual(["FR-10"], report["missing"])

    def test_duplicate_and_extra_detected(self) -> None:
        ids = list(check_fr_mapping.EXPECTED_FR) + ["FR-01", "FR-99"]
        self._write_trace(ids)
        report = check_fr_mapping.check(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual(["FR-01"], report["duplicates"])
        self.assertEqual(["FR-99"], report["extra"])

    def test_prd_cross_check(self) -> None:
        self._write_trace(list(check_fr_mapping.EXPECTED_FR))
        prd_ids = [fr for fr in check_fr_mapping.EXPECTED_FR if fr != "FR-05"] + ["FR-33"]
        prd = self._write_prd(prd_ids)
        report = check_fr_mapping.check(self.root, prd)
        self.assertFalse(report["ok"])
        self.assertEqual(["FR-33"], report["prd_missing"])
        self.assertEqual(["FR-05"], report["prd_extra"])


if __name__ == "__main__":
    unittest.main()
