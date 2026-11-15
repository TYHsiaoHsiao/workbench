"""知识库索引维护测试（M21 / FR-10）：构建、增量、校验、检索与 CLI。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main as cli_main  # noqa: E402
from contracts import validate  # noqa: E402
from knowledge_service import (  # noqa: E402
    KnowledgeIndexError,
    build_index,
    index_info,
    read_meta,
    search_index,
    split_chunks,
    verify_index,
)

INDEX_SCHEMA_NAME = "knowledge-index.schema.json"


class KnowledgeIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_kbindex_")
        self.root = Path(self._tmp)
        self.source = self.root / "kb"
        self.out = self.root / "index"
        self.source.mkdir(parents=True)
        (self.source / "01_故事.md").write_text(
            "# 悬疑短片\n\n"
            "## 节奏\n\n"
            "开场三分钟建立悬念，主角在雨夜收到一封信。\n\n"
            "## 结构\n\n"
            "三幕结构，第二幕中点反转。\n",
            encoding="utf-8",
        )
        (self.source / "02_脚本.md").write_text(
            "# 对白\n\n## 场景一\n\n雨夜，电话铃响。\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_build_creates_db_meta_and_contract(self) -> None:
        result = build_index(self.source, self.out)
        self.assertTrue(Path(result["db"]).is_file())
        self.assertTrue(Path(result["meta"]).is_file())
        meta = read_meta(self.out)
        self.assertEqual([], validate(meta, schema_name=INDEX_SCHEMA_NAME))
        self.assertEqual(2, meta["documents"])
        self.assertEqual(2, meta["files_total"])
        self.assertEqual(2, meta["files_indexed"])
        self.assertEqual("full", meta["build_mode"])
        self.assertGreaterEqual(meta["chunks"], 2)

    def test_build_accepts_custom_index_id(self) -> None:
        build_index(self.source, self.out, index_id="idx-test-0001")
        self.assertEqual("idx-test-0001", read_meta(self.out)["index_id"])

    def test_chunking_keeps_heading_and_size(self) -> None:
        body = "# 大标题\n\n## 小节\n\n" + ("长句子。" * 600)
        chunks = split_chunks(body)
        self.assertTrue(chunks)
        self.assertTrue(all(len(text) <= 900 for _head, text in chunks))
        self.assertEqual("小节", chunks[0][0])

    def test_search_chinese_term_uses_fts(self) -> None:
        build_index(self.source, self.out)
        result = search_index(self.out, "建立悬念")
        self.assertTrue(result["ok"])
        self.assertEqual("fts", result["mode"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("01_故事.md", result["results"][0]["path"])

    def test_search_short_query_falls_back_to_like(self) -> None:
        build_index(self.source, self.out)
        result = search_index(self.out, "雨夜")
        self.assertEqual("like", result["mode"])
        self.assertGreaterEqual(result["count"], 1)

    def test_search_empty_query_rejected(self) -> None:
        build_index(self.source, self.out)
        with self.assertRaises(KnowledgeIndexError):
            search_index(self.out, "   ")

    def test_incremental_reuses_unchanged(self) -> None:
        build_index(self.source, self.out)
        build_index(self.source, self.out, incremental=True)
        meta = read_meta(self.out)
        self.assertEqual("incremental", meta["build_mode"])
        self.assertEqual(0, meta["files_indexed"])
        self.assertEqual(2, meta["files_reused"])
        self.assertEqual(0, meta["files_removed"])
        self.assertEqual(2, meta["documents"])

    def test_incremental_updates_changed_and_removes_deleted(self) -> None:
        build_index(self.source, self.out)
        (self.source / "01_故事.md").write_text(
            "# 悬疑短片\n\n## 节奏\n\n开场建立悬念，结尾水落石出。\n",
            encoding="utf-8",
        )
        (self.source / "02_脚本.md").unlink()
        build_index(self.source, self.out, incremental=True)
        meta = read_meta(self.out)
        self.assertEqual(1, meta["files_indexed"])
        self.assertEqual(0, meta["files_reused"])
        self.assertEqual(1, meta["files_removed"])
        self.assertEqual(1, meta["documents"])
        result = search_index(self.out, "水落石出")
        self.assertGreaterEqual(result["count"], 1)

    def test_verify_ok_and_detects_tamper(self) -> None:
        build_index(self.source, self.out)
        report = verify_index(self.out)
        self.assertTrue(report["ok"], report["errors"])
        meta_file = Path(report["meta"])
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["documents"] += 1
        meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        tampered = verify_index(self.out)
        self.assertFalse(tampered["ok"])
        self.assertTrue(any("不一致" in item for item in tampered["errors"]))

    def test_verify_detects_missing_db(self) -> None:
        build_index(self.source, self.out)
        Path(index_info(self.out)["db"]).unlink()
        report = verify_index(self.out)
        self.assertFalse(report["ok"])

    def test_contract_rejects_invalid_meta(self) -> None:
        errors = validate({"contract_version": "0.1"}, schema_name=INDEX_SCHEMA_NAME)
        self.assertTrue(errors)

    def test_cli_build_info_search(self) -> None:
        code = cli_main(
            ["index", "build", "--source", str(self.source), "--out", str(self.out)]
        )
        self.assertEqual(0, code)
        self.assertEqual(0, cli_main(["index", "info", "--out", str(self.out)]))
        self.assertEqual(0, cli_main(["index", "verify", "--out", str(self.out)]))
        self.assertEqual(
            0,
            cli_main(
                ["index", "search", "--query", "悬念", "--out", str(self.out), "--json"]
            ),
        )

    def test_cli_failures(self) -> None:
        missing = self.root / "no-such-dir"
        self.assertNotEqual(
            0, cli_main(["index", "build", "--source", str(missing), "--out", str(self.out)])
        )
        self.assertNotEqual(0, cli_main(["index", "info", "--out", str(self.out)]))

    def test_fts5_available_in_environment(self) -> None:
        """CI 与本地 Python 均需 SQLite >= 3.34（trigram）。"""
        import sqlite3

        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='trigram')")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

class HybridSearchTest(unittest.TestCase):
    """M24：混合排序（标题/路径/短语/词项覆盖率加权）与检索模式。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_kbhybrid_")
        self.root = Path(self._tmp)
        self.source = self.root / "kb"
        self.out = self.root / "index"
        self.source.mkdir(parents=True)
        (self.source / "01_故事.md").write_text(
            "# 开头\n\n开场三分钟建立悬念，主角在雨夜收到一封信。\n",
            encoding="utf-8",
        )
        (self.source / "02_方法.md").write_text(
            "# 悬念方法\n\n建立悬念的三种方法：信息差、倒计时、危险逼近。\n",
            encoding="utf-8",
        )
        build_index(self.source, self.out)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_hybrid_heading_match_ranks_first(self) -> None:
        result = search_index(self.out, "悬念", mode="hybrid")
        self.assertEqual("hybrid", result["mode"])
        self.assertGreaterEqual(result["count"], 2)
        self.assertEqual("02_方法.md", result["results"][0]["path"])
        scores = [item["score"] for item in result["results"]]
        self.assertTrue(all(isinstance(score, (int, float)) for score in scores))
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_hybrid_short_query_uses_like_candidates(self) -> None:
        result = search_index(self.out, "悬念", mode="hybrid")
        self.assertEqual("hybrid", result["mode"])
        self.assertTrue(all(item["snippet"] for item in result["results"]))

    def test_invalid_mode_rejected(self) -> None:
        with self.assertRaises(KnowledgeIndexError):
            search_index(self.out, "悬念", mode="bogus")

    def test_forced_fts_short_query_rejected(self) -> None:
        with self.assertRaises(KnowledgeIndexError):
            search_index(self.out, "悬念", mode="fts")

    def test_hybrid_limit_respected(self) -> None:
        result = search_index(self.out, "悬念", limit=1, mode="hybrid")
        self.assertEqual(1, result["count"])

    def test_cli_hybrid_mode(self) -> None:
        code = cli_main(
            [
                "index",
                "search",
                "--query",
                "悬念",
                "--out",
                str(self.out),
                "--mode",
                "hybrid",
                "--json",
            ]
        )
        self.assertEqual(0, code)
