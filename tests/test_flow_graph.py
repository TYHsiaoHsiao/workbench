"""流程图模型与校验：flow.graph / flow.registry。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from flow import (  # noqa: E402
    FlowError,
    Graph,
    default_graph,
    load_node_types,
    order_for_mode,
    topo_order,
    validate_graph,
)


def make_node(node_id: str, node_type: str, stage: str | None = None, x: int = 0, y: int = 0) -> dict:
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
        "position": {"x": x, "y": y},
        "params": params,
    }


def make_graph(nodes: list[dict], edges: list[dict], allow_skip: bool = False) -> dict:
    return {
        "contract_version": "0.1",
        "graph_id": "flow-test",
        "name": "测试流程",
        "project": "测试项目",
        "created_at": "2026-11-15T00:00:00+08:00",
        "updated_at": "2026-11-15T00:00:00+08:00",
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "auto_advance": True,
            "allow_skip_stages": allow_skip,
            "dry_run_first": True,
        },
    }


def edge(edge_id: str, from_node: str, from_port: str, to_node: str, to_port: str) -> dict:
    return {
        "id": edge_id,
        "from": {"node": from_node, "port": from_port},
        "to": {"node": to_node, "port": to_port},
    }


class FlowGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.types = load_node_types()

    def test_node_types_registry_loads(self) -> None:
        self.assertEqual(10, len(self.types))
        self.assertEqual(
            {
                "start",
                "stage",
                "knowledge_search",
                "style_apply",
                "style_inject",
                "artifact_register",
                "check_content",
                "confirm",
                "export",
                "end",
            },
            {item.type for item in self.types.types()},
        )

    def test_linear_graph_valid(self) -> None:
        graph = make_graph(
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
        result = validate_graph(graph, self.types)
        self.assertTrue(result["ok"], msg=result)
        self.assertEqual([], result["errors"])

    def test_missing_start_detected(self) -> None:
        graph = make_graph(
            [make_node("stage-01", "stage", "01"), make_node("end", "end", x=320)],
            [edge("e1", "stage-01", "artifact", "end", "any")],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])
        self.assertTrue(any("start" in item for item in result["errors"]))

    def test_multiple_start_detected(self) -> None:
        graph = make_graph(
            [make_node("start", "start"), make_node("start-2", "start", x=300), make_node("end", "end", x=600)],
            [edge("e1", "start", "project", "start-2", "project"), edge("e2", "start-2", "project", "end", "any")],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])

    def test_cycle_detected(self) -> None:
        graph = make_graph(
            [
                make_node("start", "start"),
                make_node("stage-01", "stage", "01", x=320),
                make_node("stage-02", "stage", "02", x=640),
                make_node("end", "end", x=960),
            ],
            [
                edge("e1", "start", "project", "stage-01", "state"),
                edge("e2", "stage-01", "artifact", "stage-02", "state"),
                edge("e3", "stage-02", "artifact", "stage-01", "state"),
                edge("e4", "stage-02", "artifact", "end", "any"),
            ],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])
        self.assertTrue(any("环" in item for item in result["errors"]))

    def test_port_type_mismatch_detected(self) -> None:
        graph = make_graph(
            [make_node("start", "start"), make_node("stage-01", "stage", "01", x=320), make_node("end", "end", x=640)],
            [
                edge("e1", "start", "project", "stage-01", "artifact"),
                edge("e2", "stage-01", "artifact", "end", "any"),
            ],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])
        self.assertTrue(any("不兼容" in item for item in result["errors"]))
        self.assertTrue(any("端口" in item for item in result["errors"]))

    def test_unknown_node_type_detected(self) -> None:
        graph = make_graph(
            [make_node("start", "start"), make_node("mystery", "mystery", x=320), make_node("end", "end", x=640)],
            [edge("e1", "start", "project", "mystery", "state")],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])

    def test_duplicate_stage_detected(self) -> None:
        graph = make_graph(
            [
                make_node("start", "start"),
                make_node("stage-01a", "stage", "01", x=320),
                make_node("stage-01b", "stage", "01", x=640),
                make_node("end", "end", x=960),
            ],
            [
                edge("e1", "start", "project", "stage-01a", "state"),
                edge("e2", "stage-01a", "artifact", "stage-01b", "artifact"),
                edge("e3", "stage-01b", "artifact", "end", "any"),
            ],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])

    def test_stage_order_inversion_detected(self) -> None:
        graph = make_graph(
            [
                make_node("start", "start"),
                make_node("stage-04", "stage", "04", x=320),
                make_node("stage-02", "stage", "02", x=640),
                make_node("end", "end", x=960),
            ],
            [
                edge("e1", "start", "project", "stage-04", "state"),
                edge("e2", "stage-04", "artifact", "stage-02", "state"),
                edge("e3", "stage-02", "artifact", "end", "any"),
            ],
        )
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])

    def test_skip_stage_requires_setting(self) -> None:
        nodes = [
            make_node("start", "start"),
            make_node("stage-01", "stage", "01", x=320),
            make_node("stage-04", "stage", "04", x=640),
            make_node("end", "end", x=960),
        ]
        edges = [
            edge("e1", "start", "project", "stage-01", "state"),
            edge("e2", "stage-01", "artifact", "stage-04", "state"),
            edge("e3", "stage-04", "artifact", "end", "any"),
        ]
        strict = validate_graph(make_graph(nodes, edges, allow_skip=False), self.types)
        relaxed = validate_graph(make_graph(nodes, edges, allow_skip=True), self.types)
        self.assertFalse(strict["ok"])
        self.assertTrue(relaxed["ok"], msg=relaxed)
        self.assertTrue(relaxed["warnings"])

    def test_topo_order_is_deterministic(self) -> None:
        graph = Graph.from_dict(
            make_graph(
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
        )
        order = topo_order(graph)
        self.assertEqual(["start", "stage-01", "end"], order)
        single = order_for_mode(graph, "single", "stage-01")
        self.assertEqual(["stage-01"], single)

    def test_default_graph_skeleton(self) -> None:
        graph = default_graph("测试项目")
        self.assertEqual("flow-main", graph["graph_id"])
        self.assertEqual({"start", "end"}, {item["type"] for item in graph["nodes"]})
        self.assertEqual([], graph["edges"])

    def test_invalid_graph_object_raises(self) -> None:
        with self.assertRaises(FlowError):
            Graph.from_dict({"graph_id": "x"})

    def test_parallel_safe_flags(self) -> None:
        self.assertTrue(self.types.get("check_content").parallel_safe)
        self.assertTrue(self.types.get("end").parallel_safe)
        self.assertFalse(self.types.get("stage").parallel_safe)

    def test_parallel_settings_and_node_retries_valid(self) -> None:
        graph = make_graph(
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
        graph["settings"]["parallel"] = True
        graph["settings"]["node_retries"] = 2
        graph["nodes"][1]["retries"] = 1
        result = validate_graph(graph, self.types)
        self.assertTrue(result["ok"], msg=result)

    def test_node_retries_out_of_range(self) -> None:
        graph = make_graph(
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
        graph["nodes"][1]["retries"] = 4
        result = validate_graph(graph, self.types)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
