"""flow 执行引擎与存储：Runner / store。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project, load_state  # noqa: E402
from flow import (  # noqa: E402
    FlowError,
    Runner,
    default_graph,
    list_graphs,
    read_graph_data,
    resolve_project,
    run_flow,
    validate_graph,
    load_node_types,
    write_graph_data,
)


def make_node(node_id: str, node_type: str, stage: str | None = None, x: int = 0) -> dict:
    params: dict = {}
    if node_type == "start":
        params = {"project": "测试项目", "entry": "A"}
    elif node_type == "stage":
        params = {"stage": stage or "01", "auto_gates": True}
    elif node_type == "confirm":
        params = {"prompt": "确认继续"}
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
        "graph_id": "flow-test",
        "name": "测试流程",
        "project": project,
        "created_at": "2026-11-15T00:00:00+08:00",
        "updated_at": "2026-11-15T00:00:00+08:00",
        "nodes": nodes,
        "edges": edges,
        "settings": {"auto_advance": True, "allow_skip_stages": False, "dry_run_first": True},
    }


class FlowRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        report = create_project("流程测试", base=self.base / "projects")
        self.project = Path(report["path"])

    def _graph(self) -> dict:
        return make_graph(
            self.project.name,
            [
                make_node("start", "start"),
                make_node("stage-01", "stage", "01", x=320),
                make_node("end", "end", x=640),
            ],
            [
                edge("e1", "start", "project", "stage-01", "state"),
                edge("e2", "stage-01", "artifact", "end", "any"),
            ],
        )

    def test_dry_run_does_not_touch_state(self) -> None:
        before = load_state(self.project)
        result = Runner(self.project, self._graph(), dry_run=True).run()
        after = load_state(self.project)
        self.assertEqual("succeeded", result["run"]["status"])
        self.assertEqual(before["stage"], after["stage"])
        self.assertEqual(before["version"], after["version"])
        self.assertEqual(["planned", "planned", "planned"], [s["status"] for s in result["run"]["steps"]])

    def test_live_run_advances_stage(self) -> None:
        result = Runner(self.project, self._graph(), dry_run=False).run()
        self.assertEqual("succeeded", result["run"]["status"])
        state = load_state(self.project)
        self.assertEqual("02", state["stage"])
        self.assertEqual("v02", state["version"])

    def test_stage_mismatch_fails(self) -> None:
        graph = make_graph(
            self.project.name,
            [make_node("start", "start"), make_node("stage-05", "stage", "05", x=320), make_node("end", "end", x=640)],
            [
                edge("e1", "start", "project", "stage-05", "state"),
                edge("e2", "stage-05", "artifact", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=False).run()
        self.assertEqual("failed", result["run"]["status"])
        self.assertIn("不一致", result["run"]["steps"][1]["error"])
        self.assertEqual("01", load_state(self.project)["stage"])

    def test_confirm_pauses_and_resume(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                make_node("start", "start"),
                make_node("stage-01", "stage", "01", x=320),
                make_node("confirm-01", "confirm", x=540),
                make_node("end", "end", x=760),
            ],
            [
                edge("e1", "start", "project", "stage-01", "state"),
                edge("e2", "stage-01", "artifact", "confirm-01", "artifact"),
                edge("e3", "confirm-01", "confirmed", "end", "any"),
            ],
        )
        runner = Runner(self.project, graph, dry_run=False)
        result = runner.run()
        self.assertEqual("awaiting_confirm", result["run"]["status"])
        self.assertIsNotNone(result.get("awaiting"))
        self.assertEqual("confirm-01", result["awaiting"]["node_id"])
        self.assertEqual("waiting_confirmation", result["run"]["steps"][-1]["status"])
        resumed = runner.resume(approved=True, note="测试确认")
        self.assertEqual("succeeded", resumed["run"]["status"])
        self.assertEqual("end", resumed["run"]["steps"][-1]["node_id"])

    def test_auto_confirm_finishes(self) -> None:
        graph = make_graph(
            self.project.name,
            [
                make_node("start", "start"),
                make_node("stage-01", "stage", "01", x=320),
                make_node("confirm-01", "confirm", x=540),
                make_node("end", "end", x=760),
            ],
            [
                edge("e1", "start", "project", "stage-01", "state"),
                edge("e2", "stage-01", "artifact", "confirm-01", "artifact"),
                edge("e3", "confirm-01", "confirmed", "end", "any"),
            ],
        )
        result = Runner(self.project, graph, dry_run=True, auto_confirm=True).run()
        self.assertEqual("succeeded", result["run"]["status"])

    def test_invalid_graph_rejected(self) -> None:
        graph = self._graph()
        graph["nodes"] = graph["nodes"][:2]
        runner = Runner(self.project, graph, dry_run=True)
        with self.assertRaises(FlowError):
            runner.run()

    def test_run_record_persisted(self) -> None:
        result = run_flow(self.project, self._graph(), dry_run=True)
        run_id = result["run"]["run_id"]
        record = self.project / "00_project" / "workflows" / "runs" / f"{run_id}.json"
        self.assertTrue(record.is_file(), msg=str(record))

    def test_store_roundtrip(self) -> None:
        graph = self._graph()
        write_graph_data(self.project, graph)
        loaded = read_graph_data(self.project, "flow-test")
        self.assertEqual(graph["nodes"], loaded["nodes"])
        listed = list_graphs(self.project)
        self.assertEqual(["flow-test"], [item["graph_id"] for item in listed])
        self.assertEqual(self.project.resolve(), resolve_project(str(self.project)).resolve())

    def test_default_graph_validates_with_types(self) -> None:
        data = default_graph(self.project.name)
        result = validate_graph(data, load_node_types())
        self.assertFalse(result["ok"])  # 骨架尚未连线
        self.assertTrue(any("入边" in item or "end" in item for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
