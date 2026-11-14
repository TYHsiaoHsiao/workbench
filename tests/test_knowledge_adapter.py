"""知识服务适配器测试：只读、schema 指纹、候选召回、越界防护。"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from knowledge_service.adapter import (  # noqa: E402
    AdapterError,
    INDEX_DB_NAME,
    list_candidates,
    list_scan_files,
    open_readonly,
    probe,
    query_terms,
)
from knowledge_service.evidence import EvidenceError, resolve_under, scan_file  # noqa: E402

DOCUMENTS_SCHEMA = """
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  title TEXT,
  category TEXT,
  kind TEXT,
  size INTEGER,
  modified_ns INTEGER,
  sha256 TEXT,
  indexed INTEGER
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
"""


def make_kb(base: Path, *, schema: str | None = "aistudio-md-2", with_documents: bool = True) -> Path:
    """构造最小 aistudio-md-2 知识库夹具（SQLite + Markdown 文件）。"""
    root = base / "kb"
    root.mkdir()
    (root / "05-中日韩美高热类型片").mkdir()
    (root / "08-编剧方法书籍" / "编剧与影视专业书籍").mkdir(parents=True)
    (root / "90-隔离与待审").mkdir()
    (root / "10-小说库").mkdir()
    (root / "05-中日韩美高热类型片" / "悬疑短片结构案例.md").write_text(
        "# 案例\n\n结构：开场—反转—收束。\n反转设计需要前置伏笔。\n三幕式结构决定悬疑节奏。\n",
        encoding="utf-8",
    )
    (root / "08-编剧方法书籍" / "编剧与影视专业书籍" / "编剧方法.md").write_text(
        "# 方法\n\n三幕式结构强调冲突升级。\n反转设计要服务于人物动机。\n",
        encoding="utf-8",
    )
    (root / "90-隔离与待审" / "未审样本.md").write_text("反转设计 未审内容", encoding="utf-8")
    (root / "10-小说库" / "小说样本.md").write_text("反转设计 小说内容", encoding="utf-8")

    db_path = root / INDEX_DB_NAME
    connection = sqlite3.connect(db_path)
    try:
        if with_documents:
            connection.executescript(DOCUMENTS_SCHEMA)
            if schema is not None:
                connection.execute("INSERT INTO metadata(key, value) VALUES('schema', ?)", (schema,))
            rows = [
                ("05-中日韩美高热类型片/悬疑短片结构案例.md", "悬疑短片结构案例", "05-中日韩美高热类型片", "reference", 1),
                ("08-编剧方法书籍/编剧与影视专业书籍/编剧方法.md", "编剧方法", "08-编剧方法书籍", "method", 1),
                ("90-隔离与待审/未审样本.md", "未审样本", "90-隔离与待审", "reference", 0),
                ("10-小说库/小说样本.md", "小说样本", "10-小说库", "novel", 0),
            ]
            for path, title, category, kind, indexed in rows:
                connection.execute(
                    "INSERT INTO documents(path, title, category, kind, size, modified_ns, sha256, indexed) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (path, title, category, kind, 1, 1, "0" * 64, indexed),
                )
            try:
                connection.execute(
                    "CREATE VIRTUAL TABLE search USING fts5(terms, content='', contentless_delete=1, detail='none')"
                )
            except sqlite3.Error:  # pragma: no cover - 老版本 SQLite 兜底
                pass
        else:
            connection.execute("CREATE TABLE other (id INTEGER)")
        connection.commit()
    finally:
        connection.close()
    return root


def snapshot(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_probe_reports_fingerprint(self) -> None:
        root = make_kb(self.base)
        result = probe(root)
        self.assertEqual("aistudio-md-2", result.schema)
        self.assertEqual(4, result.documents)
        self.assertEqual(2, result.indexed_documents)
        self.assertEqual(2, result.content_files)
        self.assertIn("05-中日韩美高热类型片", result.categories)
        self.assertFalse(result.fts_external_supported)
        self.assertEqual([], result.issues)

    def test_probe_rejects_unknown_layout(self) -> None:
        root = make_kb(self.base, with_documents=False)
        with self.assertRaises(AdapterError) as ctx:
            probe(root)
        self.assertIn("documents", str(ctx.exception))

    def test_probe_reports_schema_mismatch(self) -> None:
        root = make_kb(self.base, schema="other-format")
        result = probe(root)
        self.assertTrue(any("other-format" in issue for issue in result.issues))

    def test_database_stays_read_only(self) -> None:
        root = make_kb(self.base)
        db_path = root / INDEX_DB_NAME
        before = snapshot(db_path)
        probe(root)
        list_candidates(root, ["反转设计"], ["screenplay"])
        self.assertEqual(before, snapshot(db_path))
        connection = open_readonly(db_path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE injected (id INTEGER)")
        finally:
            connection.close()

    def test_query_terms_handles_cjk_and_latin(self) -> None:
        terms = query_terms("反转设计 悬疑 Seedance2.0")
        self.assertIn("反转设计", terms)
        self.assertIn("悬疑", terms)
        self.assertTrue(any(term.startswith("Seedance") for term in terms))
        self.assertLessEqual(len(terms), 24)
        self.assertEqual(len(terms), len({term.casefold() for term in terms}))

    def test_candidates_respect_lane_and_isolation(self) -> None:
        root = make_kb(self.base)
        rows, note = list_candidates(root, ["反转设计", "悬疑"], ["screenplay", "method_book"])
        self.assertEqual("", note)
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("90-", row["path"])
            self.assertNotIn("10-", row["path"])
        self.assertTrue(any("悬疑短片结构案例" in row["path"] for row in rows))

    def test_unknown_lane_returns_no_candidates(self) -> None:
        root = make_kb(self.base)
        rows, note = list_candidates(root, ["反转设计"], ["unknown-lane"])
        self.assertEqual([], rows)
        self.assertIn("lane", note)

    def test_list_scan_files_respects_lanes_and_isolation(self) -> None:
        root = make_kb(self.base)
        rows = list_scan_files(root, ["screenplay"], limit=10)
        paths = [row["path"] for row in rows]
        self.assertTrue(any("悬疑短片结构案例" in path for path in paths))
        for path in paths:
            self.assertNotIn("90-", path)
            self.assertNotIn("10-", path)
        self.assertEqual([], list_scan_files(root, ["style_reference"], limit=10))
        self.assertEqual([], list_scan_files(root, ["screenplay"], limit=0))

    def test_scan_file_returns_line_evidence(self) -> None:
        root = make_kb(self.base)
        rel = "05-中日韩美高热类型片/悬疑短片结构案例.md"
        hits = scan_file(root, rel, ["反转设计"], max_hits=1)
        self.assertEqual(1, len(hits))
        self.assertEqual("行 4", hits[0]["page"])
        self.assertEqual("反转设计", hits[0]["hit"])
        self.assertIn("反转设计", hits[0]["snippet"])
        self.assertEqual(rel, hits[0]["path"])

    def test_scan_file_blocks_traversal(self) -> None:
        root = make_kb(self.base)
        (self.base / "outside.md").write_text("反转设计 外部文件", encoding="utf-8")
        self.assertEqual([], scan_file(root, "../outside.md", ["反转设计"]))
        with self.assertRaises(EvidenceError):
            resolve_under(root, "../outside.md")

    def test_open_readonly_missing_file(self) -> None:
        with self.assertRaises(AdapterError):
            open_readonly(self.base / "missing.sqlite")


if __name__ == "__main__":
    unittest.main()
