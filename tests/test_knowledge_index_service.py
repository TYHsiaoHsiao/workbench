"""M22：本地索引证据卡服务测试（服务 / CLI / flow 节点接入）。"""
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
from core_router.project import create_project, load_state  # noqa: E402
from flow.graph import Graph, Node  # noqa: E402
from flow.nodes import EXECUTORS, NodeContext  # noqa: E402
from flow.registry import load_node_types  # noqa: E402
from knowledge_service import (  # noqa: E402
    KnowledgeIndexServiceError,
    build_index,
    default_index_dir,
    index_ready,
    search_index_card,
)

CARD_SCHEMA = "knowledge-card.schema.json"


class KnowledgeIndexServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="wb_idxsvc_")
        self.root = Path(self._tmp)
        self.source = self.root / "kb"
        self.index = self.root / "index"
        self.source.mkdir(parents=True)
        (self.source / "01_故事.md").write_text(
            "# 悬疑短片\n\n## 节奏\n\n开场三分钟建立悬念，主角在雨夜收到一封信。\n",
            encoding="utf-8",
        )
        (self.source / "02_脚本.md").write_text(
            "# 对白\n\n## 场景一\n\n雨夜，电话铃响。\n", encoding="utf-8"
        )
        build_index(self.source, self.index)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_evidence_four_fields_and_heading_page(self) -> None:
        result = search_index_card(
            "演示", "01", "如何建立悬念", ["建立悬念"], index_dir=str(self.index)
        )
        self.assertTrue(result["ok"])
        self.assertEqual("ok", result["status"])
        card = result["card"]
        self.assertEqual([], validate(card, schema_name=CARD_SCHEMA))
        self.assertTrue(card["evidence"])
        for item in card["evidence"]:
            self.assertEqual({"path", "page", "snippet", "hit"}, set(item.keys()))
        self.assertEqual("节奏", card["evidence"][0]["page"])
        self.assertEqual("建立悬念", card["evidence"][0]["hit"])
        self.assertEqual(["story_01_05"], card["scope"])

    def test_dedupes_same_chunk_across_queries(self) -> None:
        result = search_index_card(
            "演示", "01", "问题", ["建立悬念", "开场三分钟"], index_dir=str(self.index)
        )
        hits = [item["hit"] for item in result["card"]["evidence"]]
        self.assertEqual(1, len(hits))
        self.assertIn(hits[0], {"建立悬念", "开场三分钟"})

    def test_no_evidence_status(self) -> None:
        result = search_index_card(
            "演示", "06", "问题", ["完全不存在的词"], index_dir=str(self.index)
        )
        self.assertFalse(result["ok"])
        self.assertEqual("no_evidence", result["status"])
        self.assertEqual([], result["card"]["evidence"])

    def test_short_query_falls_back_to_like(self) -> None:
        result = search_index_card(
            "演示", "01", "问题", ["悬念"], index_dir=str(self.index)
        )
        # M24：索引证据卡统一使用 hybrid 混合排序（短查询由 LIKE 候选兜底）
        self.assertEqual("hybrid", result["report"]["query_modes"]["悬念"])

    def test_parameter_validation(self) -> None:
        with self.assertRaises(KnowledgeIndexServiceError):
            search_index_card("", "01", "问题", ["悬念"], index_dir=str(self.index))
        with self.assertRaises(KnowledgeIndexServiceError):
            search_index_card("演示", "09", "问题", ["悬念"], index_dir=str(self.index))
        with self.assertRaises(KnowledgeIndexServiceError):
            search_index_card("演示", "01", "", ["悬念"], index_dir=str(self.index))
        with self.assertRaises(KnowledgeIndexServiceError):
            search_index_card("演示", "01", "问题", [], index_dir=str(self.index))
        with self.assertRaises(KnowledgeIndexServiceError):
            search_index_card("演示", "01", "问题", [""], index_dir=str(self.index))
        with self.assertRaises(KnowledgeIndexServiceError):
            search_index_card(
                "演示", "01", "问题", ["悬念"], index_dir=str(self.index), evidence_limit=0
            )

    def test_missing_index_raises_readable_error(self) -> None:
        with self.assertRaises(KnowledgeIndexServiceError) as ctx:
            search_index_card("演示", "01", "问题", ["悬念"], index_dir=str(self.root / "nope"))
        self.assertIn("索引", str(ctx.exception))

    def test_report_metadata_and_index_ready(self) -> None:
        ready = index_ready(self.index)
        result = search_index_card("演示", "01", "问题", ["建立悬念"], index_dir=str(self.index))
        report = result["report"]
        self.assertEqual("index", report["source"])
        self.assertEqual(ready["meta"]["index_id"], report["index_id"])
        self.assertEqual("full", report["build_mode"])
        self.assertEqual(2, report["documents"])
        self.assertEqual(str(self.source), report["source_root"])

    def test_default_index_dir_points_into_repo(self) -> None:
        path = default_index_dir()
        self.assertEqual(REPO_ROOT / "index", path)

    def test_cli_index_search_writes_card(self) -> None:
        card_path = self.root / "cards" / "01-candidates.json"
        exit_code = cli_main(
            [
                "knowledge",
                "search",
                "--project",
                "演示",
                "--stage",
                "01",
                "--problem",
                "如何建立悬念",
                "--query",
                "建立悬念",
                "--index",
                str(self.index),
                "--out",
                str(card_path),
                "--json",
            ]
        )
        self.assertEqual(0, exit_code)
        card = json.loads(card_path.read_text(encoding="utf-8"))
        self.assertEqual([], validate(card, schema_name=CARD_SCHEMA))

    def test_cli_index_search_missing_index_fails(self) -> None:
        exit_code = cli_main(
            [
                "knowledge",
                "search",
                "--project",
                "演示",
                "--stage",
                "01",
                "--problem",
                "问题",
                "--query",
                "悬念",
                "--index",
                str(self.root / "missing"),
            ]
        )
        self.assertEqual(1, exit_code)

    def test_flow_node_uses_index_when_configured(self) -> None:
        report = create_project("索引节点", base=self.root / "projects")
        project = Path(report["path"])
        node = Node(
            id="ks",
            type="knowledge_search",
            label="知识检索",
            position={"x": 0, "y": 0},
            params={
                "stage": "01",
                "problem": "如何建立悬念",
                "queries": ["建立悬念"],
                "index": str(self.index),
            },
        )
        graph = Graph(
            graph_id="g",
            name="g",
            project=project.name,
            nodes={"ks": node},
            edges=[],
            settings={},
        )
        ctx = NodeContext(
            project_root=project,
            node_types=load_node_types(),
            graph=graph,
            dry_run=False,
            run_id="run-test",
        )
        result = EXECUTORS["knowledge_search"](node, ctx)
        self.assertEqual("succeeded", result.status)
        card = project / "00_project" / "knowledge-cards" / "01-candidates.json"
        self.assertTrue(card.is_file())
        data = json.loads(card.read_text(encoding="utf-8"))
        self.assertTrue(data["evidence"])
        self.assertEqual(
            "00_project/knowledge-cards/01-candidates.json",
            load_state(project)["knowledge_bridge"]["last_card"],
        )

    def test_flow_node_without_index_still_works(self) -> None:
        # 无 index 参数时走原外部知识库路径；用不存在的 kb-root 只验证分支选择不崩溃。
        report = create_project("外部节点", base=self.root / "projects")
        project = Path(report["path"])
        node = Node(
            id="ks",
            type="knowledge_search",
            label="知识检索",
            position={"x": 0, "y": 0},
            params={
                "stage": "01",
                "problem": "问题",
                "queries": ["悬念"],
                "kb_root": str(self.root / "no-kb"),
            },
        )
        graph = Graph(
            graph_id="g2",
            name="g2",
            project=project.name,
            nodes={"ks": node},
            edges=[],
            settings={},
        )
        ctx = NodeContext(
            project_root=project,
            node_types=load_node_types(),
            graph=graph,
            dry_run=False,
            run_id="run-test-2",
        )
        from flow.nodes import NodeError

        with self.assertRaises(NodeError):
            EXECUTORS["knowledge_search"](node, ctx)


if __name__ == "__main__":
    unittest.main()
