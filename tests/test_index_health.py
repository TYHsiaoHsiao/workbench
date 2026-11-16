"""M29：索引健康巡检（结构/FTS 一致性/陈旧度）与 CLI。"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main as cli_main  # noqa: E402
from knowledge_service import (  # noqa: E402
    KnowledgeIndexError,
    build_index,
    check_health,
)
from knowledge_service.index_builder import INDEX_DB_NAME  # noqa: E402


class IndexHealthTest(unittest.TestCase):
    """健康巡检报告与 CLI 行为。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_idxhealth_")
        self.root = Path(self._tmp)
        self.source = self.root / "kb"
        self.out = self.root / "index"
        self.source.mkdir(parents=True)
        (self.source / "01_故事.md").write_text(
            "# 开头\n\n开场建立悬念，主角雨夜收到一封信。\n", encoding="utf-8"
        )
        (self.source / "02_方法.md").write_text(
            "# 悬疑方法\n\n用信息差和倒计时制造悬疑。\n", encoding="utf-8"
        )
        (self.source / "03_删除.md").write_text("# 临时\n\n稍后会被删除。\n", encoding="utf-8")
        build_index(self.source, self.out)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.out / INDEX_DB_NAME))

    def test_healthy_index_reports_all_ok(self) -> None:
        report = check_health(self.out, source_root=self.source)
        self.assertEqual("healthy", report["status"])
        self.assertEqual(3, report["stats"]["documents"])
        self.assertTrue(all(item["ok"] for item in report["checks"]))
        self.assertEqual([], [item for item in report["checks"] if not item["ok"]])
        self.assertEqual(0, report["stale"]["new_count"])
        self.assertIn("健康", " ".join(report["suggestions"]))

    def test_missing_index_raises(self) -> None:
        with self.assertRaises(KnowledgeIndexError):
            check_health(self.root / "missing-index")

    def test_stale_detection_counts_new_changed_removed(self) -> None:
        changed = self.source / "01_故事.md"
        changed.write_text("# 开头\n\n改写后的内容。\n", encoding="utf-8")
        stat = changed.stat()
        os.utime(changed, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        (self.source / "04_新增.md").write_text("# 新增\n\n新文件。\n", encoding="utf-8")
        (self.source / "03_删除.md").unlink()

        report = check_health(self.out, source_root=self.source)
        self.assertEqual("problems", report["status"])
        stale = report["stale"]
        self.assertEqual(1, stale["changed_count"])
        self.assertEqual(1, stale["new_count"])
        self.assertEqual(1, stale["removed_count"])
        self.assertIn("04_新增.md", stale["new"])
        self.assertIn("03_删除.md", stale["removed"])
        self.assertIn("增量", " ".join(report["suggestions"]))

    def test_orphan_chunk_detected(self) -> None:
        conn = self._db()
        try:
            conn.execute(
                "INSERT INTO chunks (path, heading, text) VALUES (?, ?, ?)",
                ("missing.md", "无主", "孤立分块"),
            )
            conn.commit()
        finally:
            conn.close()
        report = check_health(self.out)
        self.assertEqual("problems", report["status"])
        names = {item["name"] for item in report["checks"] if not item["ok"]}
        self.assertIn("orphan_chunks", names)
        self.assertIn("重建", " ".join(report["suggestions"]))

    def test_source_root_mismatch_reported(self) -> None:
        other = self.root / "other-kb"
        other.mkdir()
        (other / "x.md").write_text("# x\n\n内容。\n", encoding="utf-8")
        report = check_health(self.out, source_root=other)
        self.assertEqual("problems", report["status"])
        by_name = {item["name"]: item for item in report["checks"]}
        self.assertFalse(by_name["source_root"]["ok"])
        self.assertIn("源目录", " ".join(report["suggestions"]))

    def test_cli_health_json_exit_codes(self) -> None:
        code = cli_main(
            ["index", "health", "--out", str(self.out), "--source", str(self.source), "--json"]
        )
        self.assertEqual(0, code)

        conn = self._db()
        try:
            conn.execute(
                "INSERT INTO chunks (path, heading, text) VALUES (?, ?, ?)",
                ("orphan.md", "无主", "孤立分块"),
            )
            conn.commit()
        finally:
            conn.close()
        code = cli_main(["index", "health", "--out", str(self.out), "--json"])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
