"""知识服务 PoC 测试：证据卡契约、无假命中、只读保证与 CLI 集成。"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main as cli_main  # noqa: E402
from contracts import validate  # noqa: E402
from knowledge_service import KnowledgeService, KnowledgeServiceError  # noqa: E402
from knowledge_service.evidence import scan_file_scored  # noqa: E402

INDEX_DB_NAME = "knowledgeIndex.sqlite"


def make_kb(base: Path) -> Path:
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
    # 文件名与标题刻意不含查询词，只能靠「有限正文回退」发现
    (root / "05-中日韩美高热类型片" / "a_扫描样本1.md").write_text(
        "# 样本一\n\n开场铺垫，人物登场。\n", encoding="utf-8"
    )
    (root / "05-中日韩美高热类型片" / "a_扫描样本2.md").write_text(
        "# 样本二\n\n人物目标与阻力。\n", encoding="utf-8"
    )
    (root / "05-中日韩美高热类型片" / "z_样本三.md").write_text(
        "# 样本三\n\n第三幕回收伏笔。\n", encoding="utf-8"
    )
    # 质量排序与动作误命中过滤用例：文件名/标题刻意不同质
    (root / "05-中日韩美高热类型片" / "a_普通反转.md").write_text(
        "# 普通\n\n这里有一个反转。\n", encoding="utf-8"
    )
    (root / "05-中日韩美高热类型片" / "z_高质量反转.md").write_text(
        "# 高质量\n\n结局反转设计出现在第三幕：身份反转，真相揭晓。\n", encoding="utf-8"
    )
    (root / "05-中日韩美高热类型片" / "z_动作误命中.md").write_text(
        "# 动作\n\n他反转身倚在窗边。\n把宣传册反转过来。\n", encoding="utf-8"
    )
    (root / "90-隔离与待审" / "未审样本.md").write_text("反转设计 未审内容", encoding="utf-8")
    (root / "10-小说库" / "小说样本.md").write_text("反转设计 小说内容", encoding="utf-8")

    db_path = root / INDEX_DB_NAME
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE documents (
              id INTEGER PRIMARY KEY, path TEXT NOT NULL, title TEXT, category TEXT,
              kind TEXT, size INTEGER, modified_ns INTEGER, sha256 TEXT, indexed INTEGER
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO metadata(key, value) VALUES('schema', 'aistudio-md-2');
            """
        )
        rows = [
            ("05-中日韩美高热类型片/悬疑短片结构案例.md", "悬疑短片结构案例", "05-中日韩美高热类型片", "reference", 1),
            ("08-编剧方法书籍/编剧与影视专业书籍/编剧方法.md", "编剧方法", "08-编剧方法书籍", "method", 1),
            ("05-中日韩美高热类型片/a_扫描样本1.md", "扫描样本1", "05-中日韩美高热类型片", "reference", 1),
            ("05-中日韩美高热类型片/a_扫描样本2.md", "扫描样本2", "05-中日韩美高热类型片", "reference", 1),
            ("05-中日韩美高热类型片/z_样本三.md", "样本三", "05-中日韩美高热类型片", "reference", 1),
            ("05-中日韩美高热类型片/a_普通反转.md", "普通反转", "05-中日韩美高热类型片", "reference", 1),
            ("05-中日韩美高热类型片/z_高质量反转.md", "高质量反转", "05-中日韩美高热类型片", "reference", 1),
            ("05-中日韩美高热类型片/z_动作误命中.md", "动作误命中", "05-中日韩美高热类型片", "reference", 1),
            ("90-隔离与待审/未审样本.md", "未审样本", "90-隔离与待审", "reference", 0),
            ("10-小说库/小说样本.md", "小说样本", "10-小说库", "novel", 0),
        ]
        for path, title, category, kind, indexed in rows:
            connection.execute(
                "INSERT INTO documents(path, title, category, kind, size, modified_ns, sha256, indexed) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (path, title, category, kind, 1, 1, "0" * 64, indexed),
            )
        connection.commit()
    finally:
        connection.close()
    return root


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class KnowledgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.kb_root = make_kb(self.base)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_search_produces_contract_card_with_real_evidence(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要悬疑短片结构与反转设计参考",
            queries=[
                {"lane": "screenplay", "query": "反转设计 悬疑"},
                {"lane": "method_book", "query": "三幕式结构"},
            ],
        )
        self.assertEqual("ok", result["status"])
        card = result["card"]
        self.assertEqual([], validate(card, schema_name="knowledge-card"))
        self.assertTrue(card["evidence"])
        for item in card["evidence"]:
            self.assertTrue(item["page"].startswith("行 "))
            self.assertIn(item["hit"], item["snippet"] + item["hit"])
            self.assertNotIn("90-", item["path"])
            self.assertNotIn("10-", item["path"])
        self.assertEqual(["story_01_05"], card["scope"])

    def test_no_hit_never_fabricates_evidence(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要完全无关的参考",
            queries=[{"lane": "screenplay", "query": "量子纠缠 黑洞"}],
        )
        self.assertEqual("no_candidates", result["status"])
        self.assertEqual([], result["card"]["evidence"])
        self.assertEqual([], result["card"]["candidates"])
        self.assertEqual({"by": "", "at": ""}, result["card"]["confirmed"])
        self.assertIn("不得", result["report"]["statement"])

    def test_fallback_finds_content_when_metadata_misses(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要伏笔回收参考",
            queries=[{"lane": "screenplay", "query": "伏笔"}],
        )
        self.assertEqual("ok", result["status"])
        self.assertEqual([], validate(result["card"], schema_name="knowledge-card"))
        fallback = result["report"]["fallback"]
        self.assertTrue(fallback["enabled"])
        self.assertEqual("evidence_below_limit", fallback["trigger"])
        self.assertGreater(fallback["files_scanned"], 0)
        self.assertTrue(any("z_样本三" in item["path"] for item in result["card"]["evidence"]))
        self.assertTrue(any("z_样本三" in path for path in result["card"]["candidates"]))
        self.assertEqual(0, result["report"]["lane_candidates"]["screenplay"])

    def test_fallback_budget_is_bounded(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要伏笔参考",
            queries=[{"lane": "screenplay", "query": "伏笔"}],
            fallback_max_files=2,
        )
        self.assertEqual("no_candidates", result["status"])
        self.assertEqual([], result["card"]["evidence"])
        self.assertEqual(2, result["report"]["fallback"]["files_scanned"])

    def test_fallback_can_be_disabled(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要伏笔参考",
            queries=[{"lane": "screenplay", "query": "伏笔"}],
            fallback=False,
        )
        self.assertEqual("no_candidates", result["status"])
        self.assertEqual([], result["card"]["evidence"])
        self.assertFalse(result["report"]["fallback"]["enabled"])
        self.assertEqual(0, result["report"]["fallback"]["files_scanned"])

    def test_evidence_sorted_by_quality(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要反转结构参考",
            queries=[{"lane": "screenplay", "query": "反转 身份"}],
        )
        self.assertEqual("ok", result["status"])
        evidence = result["card"]["evidence"]
        self.assertTrue(evidence)
        self.assertTrue(evidence[0]["path"].endswith("z_高质量反转.md"))
        self.assertIn("身份", evidence[0]["snippet"])
        self.assertEqual({"path", "page", "snippet", "hit"}, set(evidence[0].keys()))
        quality = result["report"]["evidence_quality"]
        self.assertEqual("score", quality["sorted_by"])
        self.assertGreaterEqual(quality["phrase_hits"], 1)
        self.assertGreaterEqual(quality["cooccurrence_hits"], 1)
        self.assertGreaterEqual(quality["top_score"], 8)

    def test_action_mis_hits_are_filtered(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要反转参考",
            queries=[{"lane": "screenplay", "query": "反转"}],
        )
        self.assertGreaterEqual(
            result["report"]["evidence_quality"]["filtered_mis_hits"], 2
        )
        self.assertFalse(
            any("z_动作误命中" in item["path"] for item in result["card"]["evidence"])
        )

    def test_scan_file_scored_filters_action_usage(self) -> None:
        hits, stats = scan_file_scored(
            self.kb_root, "05-中日韩美高热类型片/z_动作误命中.md", ["反转"]
        )
        self.assertEqual([], hits)
        self.assertEqual(2, stats["filtered"])

    def test_scan_file_scored_rewards_phrase_and_cooccurrence(self) -> None:
        hits, _ = scan_file_scored(
            self.kb_root, "05-中日韩美高热类型片/z_高质量反转.md", ["反转", "身份"]
        )
        self.assertTrue(hits)
        quality = hits[0]["quality"]
        self.assertTrue(quality["phrase"])
        self.assertTrue(quality["cooccurrence"])
        self.assertGreaterEqual(quality["score"], 8)

    def test_low_confidence_evidence_dropped_when_high_exists(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="05",
            problem="需要反转参考",
            queries=[{"lane": "screenplay", "query": "反转"}],
        )
        quality = result["report"]["evidence_quality"]
        self.assertGreaterEqual(quality["high_confidence_evidence"], 2)
        self.assertGreaterEqual(quality["low_confidence_dropped"], 1)
        self.assertFalse(
            any("a_普通反转" in item["path"] for item in result["card"]["evidence"])
        )

    def test_stage_scope_mapping(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        result = service.search(
            project="demo",
            stage="08",
            problem="镜头连续性参考",
            queries=[{"lane": "screenplay", "query": "反转设计"}],
        )
        self.assertEqual(["camera_08"], result["card"]["scope"])

    def test_invalid_inputs_raise(self) -> None:
        service = KnowledgeService(kb_root=self.kb_root)
        with self.assertRaises(KnowledgeServiceError):
            service.search(project="demo", stage="09", problem="x", queries=[{"lane": "screenplay", "query": "反转"}])
        with self.assertRaises(KnowledgeServiceError):
            service.search(project="", stage="05", problem="x", queries=[{"lane": "screenplay", "query": "反转"}])
        with self.assertRaises(KnowledgeServiceError):
            service.search(project="demo", stage="05", problem=" ", queries=[{"lane": "screenplay", "query": "反转"}])
        with self.assertRaises(KnowledgeServiceError):
            service.search(project="demo", stage="05", problem="x", queries=[{"lane": "unknown", "query": "反转"}])

    def test_search_does_not_modify_knowledge_base(self) -> None:
        db_path = self.kb_root / INDEX_DB_NAME
        before = digest(db_path)
        mtime = db_path.stat().st_mtime_ns
        service = KnowledgeService(kb_root=self.kb_root)
        service.search(
            project="demo",
            stage="05",
            problem="结构参考",
            queries=[{"lane": "screenplay", "query": "反转设计"}],
        )
        self.assertEqual(before, digest(db_path))
        self.assertEqual(mtime, db_path.stat().st_mtime_ns)

    def test_cli_probe_and_search(self) -> None:
        out_path = self.base / "card.json"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            probe_code = cli_main(["knowledge", "probe", "--kb-root", str(self.kb_root), "--json"])
            search_code = cli_main(
                [
                    "knowledge", "search",
                    "--project", "demo",
                    "--stage", "05",
                    "--problem", "需要悬疑结构参考",
                    "--query", "screenplay:反转设计 悬疑",
                    "--kb-root", str(self.kb_root),
                    "--out", str(out_path),
                    "--json",
                ]
            )
        self.assertEqual(0, probe_code)
        self.assertEqual(0, search_code)
        self.assertTrue(out_path.is_file())
        card = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual([], validate(card, schema_name="knowledge-card"))
        self.assertTrue(card["evidence"])

    def test_cli_probe_reports_incompatible_layout(self) -> None:
        bad = self.base / "bad"
        bad.mkdir()
        db = bad / INDEX_DB_NAME
        connection = sqlite3.connect(db)
        try:
            connection.execute("CREATE TABLE other (id INTEGER)")
            connection.commit()
        finally:
            connection.close()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli_main(["knowledge", "probe", "--kb-root", str(bad)])
        self.assertEqual(1, code)
        self.assertIn("documents", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
