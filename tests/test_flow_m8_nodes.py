"""M8 复合节点：knowledge_adopt / style_bind / generate（含 dry-run）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.memory import load_memory  # noqa: E402
from core_router.project import create_project, load_state, save_state  # noqa: E402
from flow import Runner  # noqa: E402
from generate.jobs import jobs_dir  # noqa: E402


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
        "graph_id": "flow-m8",
        "name": "M8 复合节点",
        "project": project,
        "created_at": "2026-11-15T00:00:00+08:00",
        "updated_at": "2026-11-15T00:00:00+08:00",
        "nodes": nodes,
        "edges": edges,
        "settings": {"auto_advance": True, "allow_skip_stages": False, "dry_run_first": False},
    }


def make_card(project: str, confirmed_by: str = "用户") -> dict:
    return {
        "contract_version": "1.0",
        "card_id": "card-m8-test",
        "project": project,
        "stage": "01",
        "query_profile": {
            "problem": "开场钩子怎么写",
            "queries": [{"lane": "screenplay", "query": "钩子"}],
        },
        "evidence": [
            {
                "path": "05-剧本/示例剧本.md",
                "page": "第 3 页",
                "snippet": "开场三行内抛出问题。",
                "hit": "钩子",
            },
            {
                "path": "08-分析/示例方法.md",
                "page": "行 12",
                "snippet": "先给结果再给原因。",
                "hit": "结构",
            },
        ],
        "candidates": [],
        "selected_documents": [],
        "deep_read_selected": False,
        "confirmed": {"by": confirmed_by, "at": "2026-11-15T10:00:00+08:00"},
        "scope": ["story_01_05"],
    }


class M8CompoundNodesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        report = create_project("复合节点", base=Path(self.tmp.name) / "projects")
        self.project = Path(report["path"])

    def _start(self) -> dict:
        return make_node("start", "start", {"project": self.project.name, "entry": "A"})

    def _write_card(self, confirmed_by: str = "用户") -> str:
        card = make_card(self.project.name, confirmed_by=confirmed_by)
        target = self.project / "01_story" / "knowledge-card.json"
        target.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        return "01_story/knowledge-card.json"

    def test_knowledge_adopt_writes_reference_memory(self) -> None:
        card_path = self._write_card()
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("adopt", "knowledge_adopt", {"card": card_path}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "adopt", "state"),
                edge("e2", "adopt", "reference", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        memory = load_memory(self.project)
        entries = memory["entries"]
        self.assertEqual(["参考方法001", "参考方法002"], [entry["id"] for entry in entries])
        self.assertEqual(["screenplay", "method_book"], [entry["type"] for entry in entries])
        self.assertEqual("05-剧本/示例剧本.md", entries[0]["local_path"])
        self.assertEqual("第 3 页", entries[0]["page_hits"])
        state = load_state(self.project)
        self.assertEqual(["参考方法001", "参考方法002"], state["references"])
        self.assertEqual("on", state["knowledge_bridge"]["status"])
        self.assertEqual(2, len(state["knowledge_bridge"]["confirmed_references"]))
        outputs = " ".join(
            str(item) for step in result["run"]["steps"] for item in (step.get("outputs") or [])
        )
        self.assertIn("已采纳 2 条参考方法", outputs)

    def test_knowledge_adopt_requires_confirmation(self) -> None:
        card_path = self._write_card(confirmed_by="")
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("adopt", "knowledge_adopt", {"card": card_path}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "adopt", "state"),
                edge("e2", "adopt", "reference", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("failed", result["run"]["status"])
        error = str(result["run"]["steps"][1].get("error") or "")
        self.assertIn("尚未确认", error)
        self.assertEqual([], load_memory(self.project)["entries"])

    def test_knowledge_adopt_dedupes(self) -> None:
        card_path = self._write_card()
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("adopt", "knowledge_adopt", {"card": card_path}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "adopt", "state"),
                edge("e2", "adopt", "reference", "end", "any"),
            ],
        )
        Runner(self.project, graph, dry_run=False).run()
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        self.assertEqual(2, len(load_memory(self.project)["entries"]))
        outputs = " ".join(
            str(item) for step in result["run"]["steps"] for item in (step.get("outputs") or [])
        )
        self.assertIn("无新的可采纳证据", outputs)

    def test_knowledge_adopt_dry_run_does_not_write(self) -> None:
        card_path = self._write_card()
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("adopt", "knowledge_adopt", {"card": card_path}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "adopt", "state"),
                edge("e2", "adopt", "reference", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=True).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        self.assertEqual([], load_memory(self.project)["entries"])

    def test_style_bind_writes_style_reference(self) -> None:
        profile_rel = "00_project/style-cards/test-style.json"
        profile = {
            "name": "测试风格",
            "lighting": "侧逆光",
            "lens": "35mm",
            "palette": [{"name": "青", "ratio": 40}, {"name": "琥珀", "ratio": 25}],
        }
        profile_path = self.project / profile_rel
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        state = load_state(self.project)
        state["style"] = {"status": "on", "profile_path": profile_rel, "note": ""}
        save_state(self.project, state)

        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("bind", "style_bind", {"style": "", "scope": ["image_06", "camera_08"]}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "bind", "state"),
                edge("e2", "bind", "reference", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        entries = load_memory(self.project)["entries"]
        self.assertEqual(1, len(entries))
        self.assertEqual("style_reference", entries[0]["type"])
        self.assertEqual(profile_rel, entries[0]["local_path"])
        self.assertEqual(["image_06", "camera_08"], entries[0]["scope"])
        state = load_state(self.project)
        self.assertIn(entries[0]["id"], state["references"])

        result = Runner(self.project, graph, dry_run=False).run()
        outputs = " ".join(
            str(item) for step in result["run"]["steps"] for item in (step.get("outputs") or [])
        )
        self.assertIn("风格参考已存在", outputs)
        self.assertEqual(1, len(load_memory(self.project)["entries"]))

    def test_generate_node_submits_dry_run_job(self) -> None:
        prompt = "镜头 01：雨夜巷口，女人回头看向镜头，霓虹反光。"
        prompt_path = self.project / "06_prompts" / "shot-01.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node(
                    "gen",
                    "generate",
                    {"provider": "mock", "prompt_path": "06_prompts/shot-01.txt", "shot": "01"},
                    x=320,
                ),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "gen", "state"),
                edge("e2", "gen", "generation", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        jobs = list(jobs_dir(self.project).glob("gen-*.json"))
        self.assertEqual(1, len(jobs))
        job = json.loads(jobs[0].read_text(encoding="utf-8"))
        self.assertEqual("mock", job["provider"])
        self.assertTrue(job["dry_run"])
        outputs = " ".join(
            str(item) for step in result["run"]["steps"] for item in (step.get("outputs") or [])
        )
        self.assertIn(job["job_id"], outputs)

    def test_generate_node_requires_prompt(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("gen", "generate", {"provider": "mock"}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "gen", "state"),
                edge("e2", "gen", "generation", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("failed", result["run"]["status"])
        self.assertIn("缺少 prompt_path", str(result["run"]["steps"][1].get("error") or ""))

    def test_generate_node_dry_run_plans_only(self) -> None:
        prompt_path = self.project / "06_prompts" / "shot-01.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("镜头：雨夜。", encoding="utf-8")
        graph = make_graph(
            self.project.name,
            [
                self._start(),
                make_node("gen", "generate", {"provider": "mock", "prompt_path": "06_prompts/shot-01.txt"}, x=320),
                make_node("end", "end", {}, x=640),
            ],
            [
                edge("e1", "start", "project", "gen", "state"),
                edge("e2", "gen", "generation", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=True).run()
        self.assertEqual("succeeded", result["run"]["status"], msg=result)
        self.assertEqual([], list(jobs_dir(self.project).glob("gen-*.json")))


if __name__ == "__main__":
    unittest.main()
