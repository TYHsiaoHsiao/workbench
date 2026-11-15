"""flow 能力节点：产物登记 / 内容检查 / 导出 / 知识检索与风格（dry-run）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project, load_state, save_state  # noqa: E402
from flow import Runner  # noqa: E402


def make_node(node_id: str, node_type: str, params: dict, x: int = 0) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": node_type,
        "position": {"x": x, "y": 140},
        "params": params,
    }


def edge(edge_id: str, from_node: str, from_port: str, to_node: str, to_port: str) -> dict:
    return {
        "id": edge_id,
        "from": {"node": from_node, "port": from_port},
        "to": {"node": to_node, "port": to_port},
    }


def make_graph(project: str, nodes: list[dict], edges: list[dict]) -> dict:
    return {
        "contract_version": "0.1",
        "graph_id": "flow-capability",
        "name": "能力节点流程",
        "project": project,
        "created_at": "2026-11-15T00:00:00+08:00",
        "updated_at": "2026-11-15T00:00:00+08:00",
        "nodes": nodes,
        "edges": edges,
        "settings": {"auto_advance": True, "allow_skip_stages": False, "dry_run_first": False},
    }


class FlowCapabilityNodesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        report = create_project("能力节点", base=base / "projects")
        self.project = Path(report["path"])

    def _start(self) -> dict:
        return make_node("start", "start", {"project": self.project.name, "entry": "A"})

    def test_artifact_register_node(self) -> None:
        target = self.project / "01_story" / "synopsis.md"
        target.write_text("# 大纲\n\n测试内容。\n", encoding="utf-8")
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node(
                    "reg",
                    "artifact_register",
                    {"stage": "01", "kind": "大纲", "paths": ["01_story/synopsis.md"]},
                    x=320,
                ),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "reg", "state"),
                edge("e2", "reg", "artifact", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        state = load_state(self.project)
        self.assertIn("大纲", state["stage_artifacts"]["01"])
        self.assertTrue(any(entry["action"] == "artifact_registered" for entry in state["revision_log"]))

    def test_check_content_node_passes_on_clean_project(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("check", "check_content", {"fail_on_error": True}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "check", "state"),
                edge("e2", "check", "log", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)

    def test_check_content_node_fails_on_missing_style_card(self) -> None:
        state = load_state(self.project)
        state["style"] = {"status": "on", "profile_path": "00_project/style-cards/missing.json", "note": ""}
        save_state(self.project, state)
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("check", "check_content", {"fail_on_error": True}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "check", "state"),
                edge("e2", "check", "log", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("failed", result["run"]["status"])
        self.assertIn("内容检查失败", result["run"]["steps"][1]["error"])

    def test_export_node(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("export", "export", {}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "export", "state"),
                edge("e2", "export", "artifact", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        outputs = " ".join(str(item) for step in result["run"]["steps"] for item in (step.get("outputs") or []))
        self.assertIn("导出", outputs)
        self.assertTrue(list((self.project / "00_project" / "history").glob("project-*.zip")))

    def test_knowledge_search_dry_run(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node(
                    "kb",
                    "knowledge_search",
                    {
                        "stage": "01",
                        "problem": "悬疑短片需要反转",
                        "queries": ["screenplay:悬疑 反转"],
                        "candidates_limit": 5,
                        "evidence_limit": 3,
                    },
                    x=320,
                ),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "kb", "state"),
                edge("e2", "kb", "knowledge_card", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=True).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        self.assertEqual(["planned"] * 3, [step["status"] for step in result["run"]["steps"]])

    def test_style_apply_dry_run(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("style", "style_apply", {"style": "002", "tool": "mj"}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "style", "state"),
                edge("e2", "style", "style_card", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=True).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)


if __name__ == "__main__":
    unittest.main()
