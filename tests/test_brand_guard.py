"""品牌守卫测试：归一化、文本/Office/allowlist、报告不泄露明文。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from brand_guard import BrandGuardError, load_wordlist, normalize, scan, scan_text  # noqa: E402

WORDLIST = REPO_ROOT / "packages" / "brand_guard" / "wordlist.b64"


def _terms() -> list[str]:
    return load_wordlist(WORDLIST)


def _write_min_repo(tmp: Path, wordlist_lines: str) -> None:
    """在 tmp 下构造最小可扫描仓库（词表内容以 base64 形式写入）。"""
    (tmp / "wordlist.b64").write_text(wordlist_lines, encoding="utf-8")
    config = {
        "version": "1.0",
        "wordlist": "wordlist.b64",
        "allowlist": "allow.json",
        "skip_dirs": [],
        "skip_exts": [".png"],
        "max_file_mb": 1,
        "targets": [{"name": "all", "path": "."}],
    }
    (tmp / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp / "allow.json").write_text(
        json.dumps({"version": "1.0", "entries": []}), encoding="utf-8"
    )


class BrandGuardTest(unittest.TestCase):
    def test_wordlist_decodes_terms(self) -> None:
        terms = _terms()
        self.assertEqual(2, len(terms))
        self.assertTrue(all(term for term in terms))

    def test_wordlist_file_contains_no_plaintext(self) -> None:
        text = WORDLIST.read_text(encoding="utf-8")
        for term in _terms():
            self.assertNotIn(term, text)

    def test_normalize_removes_separators(self) -> None:
        term = _terms()[0]
        spaced = " ".join(term)
        self.assertEqual(normalize(term), normalize(spaced))
        self.assertEqual(normalize(term), normalize(term.lower()))

    def test_scan_text_detects_term(self) -> None:
        terms = _terms()
        hits = scan_text(f"前缀 {terms[0]} 后缀", terms, "sample.md")
        self.assertEqual(1, len(hits))
        self.assertEqual("term#1", hits[0]["term"])
        self.assertEqual(1, hits[0]["line"])

    def test_scan_text_detects_variant(self) -> None:
        terms = _terms()
        variant = "-".join(terms[0].lower())
        hits = scan_text(variant, terms, "sample.md")
        self.assertEqual(1, len(hits))

    def test_scan_text_clean(self) -> None:
        self.assertEqual([], scan_text("这是完全干净的文本。", _terms(), "clean.md"))

    def test_safe_token_is_ignored(self) -> None:
        terms = _terms()
        token = "aistudio-md-2"
        self.assertTrue(scan_text(f"引用 {token} 格式", terms, "doc.md"))
        self.assertEqual(
            [], scan_text(f"引用 {token} 格式", terms, "doc.md", (token,))
        )

    def test_scan_min_repo_reports_hit_without_plaintext(self) -> None:
        terms = _terms()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            lines = WORDLIST.read_text(encoding="utf-8")
            _write_min_repo(tmp, lines)
            (tmp / "sample.md").write_text(f"正文 {terms[0]} 正文\n", encoding="utf-8")
            report = scan(repo_root=tmp, config_path=tmp / "config.json")
            self.assertFalse(report["ok"])
            paths = {hit["path"] for hit in report["hits"]}
            self.assertIn("sample.md", paths)
            dumped = json.dumps(report, ensure_ascii=False)
            for term in terms:
                self.assertNotIn(term, dumped)

    def test_scan_reports_clean_repo(self) -> None:
        report = scan(repo_root=REPO_ROOT)
        self.assertTrue(report["ok"], msg=json.dumps(report["hits"], ensure_ascii=False))
        self.assertEqual([], report["hits"])
        self.assertGreater(report["scanned"], 0)

    def test_allowlist_skips_tree(self) -> None:
        terms = _terms()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            _write_min_repo(tmp, WORDLIST.read_text(encoding="utf-8"))
            (tmp / "allow.json").write_text(
                json.dumps({"version": "1.0", "entries": [{"path": "corpus"}]}),
                encoding="utf-8",
            )
            (tmp / "corpus").mkdir()
            (tmp / "corpus" / "novel.md").write_text(terms[0], encoding="utf-8")
            report = scan(repo_root=tmp, config_path=tmp / "config.json")
            self.assertTrue(report["ok"], msg=json.dumps(report["hits"], ensure_ascii=False))

    def test_office_member_is_scanned(self) -> None:
        terms = _terms()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            _write_min_repo(tmp, WORDLIST.read_text(encoding="utf-8"))
            xlsx = tmp / "office.xlsx"
            sheet = (
                "<worksheet><sheetData><row><c><is><t>"
                + terms[0]
                + "</t></is></c></row></sheetData></worksheet>"
            )
            with zipfile.ZipFile(xlsx, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            report = scan(repo_root=tmp, config_path=tmp / "config.json")
            self.assertFalse(report["ok"])
            paths = [hit["path"] for hit in report["hits"]]
            self.assertTrue(any("office.xlsx!" in path for path in paths))

    def test_skip_exts_are_not_scanned(self) -> None:
        terms = _terms()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            _write_min_repo(tmp, WORDLIST.read_text(encoding="utf-8"))
            (tmp / "image.png").write_text(terms[0], encoding="utf-8")
            report = scan(repo_root=tmp, config_path=tmp / "config.json")
            self.assertTrue(report["ok"])
            reasons = {item["reason"] for item in report["skipped"]}
            self.assertIn("skip_ext", reasons)

    def test_missing_wordlist_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / "config.json").write_text(
                json.dumps({"wordlist": "missing.b64", "allowlist": "allow.json",
                            "targets": []}),
                encoding="utf-8",
            )
            with self.assertRaises(BrandGuardError):
                scan(repo_root=tmp, config_path=tmp / "config.json")


if __name__ == "__main__":
    unittest.main()
