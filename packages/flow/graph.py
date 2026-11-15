"""流程图模型、校验规则与拓扑排序（契约 v0.1）。

设计要点：
- 图只表达"流程意图 + 布局"，不复制业务数据；执行结果写回项目 state.json。
- 校验分两层：契约 schema（结构） + 语义规则（start/end、端口兼容、阶段约束）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts import load_schema, validate

GRAPH_SCHEMA = "flow-graph.schema.json"
STAGE_ORDER = [f"0{index}" for index in range(1, 9)]

# 端口类型兼容表：输出端口 -> 允许连接的输入端口类型
PORT_COMPAT: dict[str, set[str]] = {
    "project": {"project", "state", "text", "card", "log"},
    "state": {"state"},
    "artifact": {"artifact", "state", "text", "card", "log", "any"},
    "log": {"log", "text", "card", "any"},
    "text": {"text", "card", "log", "any"},
    "card": {"card", "text", "log", "any"},
    "confirmed": {"confirmed", "artifact", "log", "any"},
    "knowledge_card": {"knowledge_card", "card", "text", "log", "artifact", "any"},
    "style_card": {"style_card", "card", "text", "log", "artifact", "any"},
    "injection": {"injection", "artifact", "log", "text", "any"},
    "any": {"any"},
}


class FlowError(Exception):
    """流程图校验或执行错误。"""


def _normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """保留扩展设置（parallel / node_retries），并统一成引擎可消费的类型。"""
    normalized: dict[str, Any] = dict(settings or {})
    normalized["auto_advance"] = bool(normalized.get("auto_advance", False))
    normalized["allow_skip_stages"] = bool(normalized.get("allow_skip_stages", False))
    normalized["dry_run_first"] = bool(normalized.get("dry_run_first", True))
    normalized["parallel"] = bool(normalized.get("parallel", False))
    try:
        normalized["node_retries"] = max(0, min(3, int(normalized.get("node_retries", 0) or 0)))
    except (TypeError, ValueError):
        normalized["node_retries"] = 0
    return normalized


def port_compatible(out_port: str, in_port: str) -> bool:
    """输出端口能否连接到输入端口（in_port=any 表示任意）。"""
    if in_port == "any":
        return True
    return in_port in PORT_COMPAT.get(out_port, set())


@dataclass
class Node:
    id: str
    type: str
    label: str
    position: dict[str, float]
    params: dict[str, Any] = field(default_factory=dict)
    disabled: bool = False
    note: str = ""
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "position": {"x": float(self.position.get("x", 0)), "y": float(self.position.get("y", 0))},
            "params": dict(self.params),
        }
        if self.disabled:
            data["disabled"] = True
        if self.note:
            data["note"] = self.note
        if self.retries:
            data["retries"] = int(self.retries)
        return data


@dataclass
class Edge:
    id: str
    from_node: str
    from_port: str
    to_node: str
    to_port: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": {"node": self.from_node, "port": self.from_port},
            "to": {"node": self.to_node, "port": self.to_port},
        }


@dataclass
class Graph:
    graph_id: str
    name: str
    project: str
    nodes: dict[str, Node]
    edges: list[Edge]
    settings: dict[str, Any]
    created_at: str = ""
    updated_at: str = ""
    canvas: dict[str, Any] = field(default_factory=dict)
    contract_version: str = "0.1"

    # -- 构造 ---------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        try:
            nodes = {
                item["id"]: Node(
                    id=item["id"],
                    type=item["type"],
                    label=item.get("label") or item["id"],
                    position=dict(item.get("position") or {}),
                    params=dict(item.get("params") or {}),
                    disabled=bool(item.get("disabled", False)),
                    note=str(item.get("note") or ""),
                    retries=int(item.get("retries") or 0),
                )
                for item in data["nodes"]
            }
            edges = [
                Edge(
                    id=item["id"],
                    from_node=item["from"]["node"],
                    from_port=item["from"]["port"],
                    to_node=item["to"]["node"],
                    to_port=item["to"]["port"],
                )
                for item in data.get("edges") or []
            ]
        except (KeyError, TypeError) as exc:  # pragma: no cover - schema 已先拦一层
            raise FlowError(f"流程图结构不完整: {exc}") from exc
        settings = dict(data.get("settings") or {})
        return cls(
            graph_id=str(data.get("graph_id") or ""),
            name=str(data.get("name") or ""),
            project=str(data.get("project") or ""),
            nodes=nodes,
            edges=edges,
            settings=_normalize_settings(settings),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            canvas=dict(data.get("canvas") or {}),
            contract_version=str(data.get("contract_version") or "0.1"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "graph_id": self.graph_id,
            "name": self.name,
            "project": self.project,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "canvas": dict(self.canvas),
            "settings": dict(self.settings),
            "nodes": [self.nodes[node_id].to_dict() for node_id in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    # -- 查询 ---------------------------------------------------------
    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise FlowError(f"节点不存在: {node_id}") from exc

    def outgoing(self, node_id: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.from_node == node_id]

    def incoming(self, node_id: str) -> list[Edge]:
        return [edge for edge in self.edges if edge.to_node == node_id]

    def stage_of(self, node_id: str) -> str | None:
        node = self.nodes.get(node_id)
        if node and node.type == "stage":
            value = node.params.get("stage")
            return str(value) if value else None
        return None


def _sort_key(graph: Graph) -> Any:
    def key(node_id: str) -> tuple[float, float, str]:
        node = graph.nodes[node_id]
        return (float(node.position.get("y", 0)), float(node.position.get("x", 0)), node_id)

    return key


def topo_order(graph: Graph) -> list[str]:
    """Kahn 拓扑排序；同层按画布位置稳定排序。"""
    indegree = {node_id: 0 for node_id in graph.nodes}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in graph.nodes}
    for edge in graph.edges:
        if edge.from_node in adjacency and edge.to_node in indegree:
            adjacency[edge.from_node].append(edge.to_node)
            indegree[edge.to_node] += 1
    key = _sort_key(graph)
    ready = sorted([node_id for node_id, degree in indegree.items() if degree == 0], key=key)
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
        ready.sort(key=key)
    if len(order) != len(graph.nodes):
        # 找出环上的节点提示（有入度剩余且未处理）
        remaining = [node_id for node_id in graph.nodes if node_id not in order]
        raise FlowError("流程图存在环，无法确定执行顺序: " + ", ".join(sorted(remaining)))
    return order


def ancestors(graph: Graph, node_id: str) -> set[str]:
    """返回 node_id 的全部上游节点（不含自身）。"""
    if node_id not in graph.nodes:
        raise FlowError(f"节点不存在: {node_id}")
    result: set[str] = set()
    stack = [edge.from_node for edge in graph.incoming(node_id)]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(edge.from_node for edge in graph.incoming(current))
    return result


def order_for_mode(graph: Graph, mode: str = "full", target: str | None = None) -> list[str]:
    """按运行模式给出执行顺序。"""
    full = topo_order(graph)
    if mode == "full":
        return full
    if not target:
        raise FlowError(f"运行模式 {mode} 需要指定目标节点")
    if target not in graph.nodes:
        raise FlowError(f"节点不存在: {target}")
    if mode == "single":
        return [target]
    if mode == "to_node":
        keep = ancestors(graph, target) | {target}
        return [node_id for node_id in full if node_id in keep]
    raise FlowError(f"未知运行模式: {mode}")


def validate_graph(data: dict[str, Any], node_types: Any) -> dict[str, Any]:
    """校验流程图：契约 + 语义规则。返回 {ok, errors, warnings}。"""
    errors: list[str] = list(validate(data, schema_name=GRAPH_SCHEMA))
    warnings: list[str] = []
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    graph = Graph.from_dict(data)
    seen_ids: set[str] = set()
    for node_id in graph.nodes:
        if node_id in seen_ids:
            errors.append(f"节点 id 重复: {node_id}")
        seen_ids.add(node_id)

    start_ids = [nid for nid, node in graph.nodes.items() if node.type == "start"]
    end_ids = [nid for nid, node in graph.nodes.items() if node.type == "end"]
    if len(start_ids) != 1:
        errors.append(f"必须且只能有一个 start 节点（当前 {len(start_ids)} 个）")
    if not end_ids:
        errors.append("至少需要一个 end 节点")

    for node in graph.nodes.values():
        type_spec = node_types.get(node.type)
        if type_spec is None:
            errors.append(f"节点 {node.id} 的类型未注册: {node.type}")
            continue
        for problem in node_types.validate_params(node.type, node.params):
            errors.append(f"节点 {node.id} 参数非法: {problem}")
        if node.type == "stage":
            stage = str(node.params.get("stage") or "")
            if stage not in STAGE_ORDER:
                errors.append(f"节点 {node.id} 的 stage 非法: {stage}")
        if node.type != "start" and not graph.incoming(node.id):
            errors.append(f"节点 {node.id} 缺少入边（除 start 外每个节点至少一个入边）")
        if node.type == "start" and graph.incoming(node.id):
            errors.append(f"start 节点 {node.id} 不应有入边")
        if node.type == "end" and graph.outgoing(node.id):
            errors.append(f"end 节点 {node.id} 不应有出边")
        if type_spec.ports_out and node.type != "end" and not graph.outgoing(node.id):
            errors.append(f"节点 {node.id} 有输出端口但没有下游连线")

    for edge in graph.edges:
        source = graph.nodes.get(edge.from_node)
        target = graph.nodes.get(edge.to_node)
        if source is None or target is None:
            errors.append(f"连线 {edge.id} 引用了不存在的节点")
            continue
        source_spec = node_types.get(source.type)
        target_spec = node_types.get(target.type)
        if source_spec is None or target_spec is None:
            continue
        if edge.from_port not in source_spec.ports_out:
            errors.append(f"连线 {edge.id}: 节点 {source.id} 没有输出端口 {edge.from_port}")
            continue
        if edge.to_port not in target_spec.ports_in:
            errors.append(f"连线 {edge.id}: 节点 {target.id} 没有输入端口 {edge.to_port}")
            continue
        if not port_compatible(edge.from_port, edge.to_port):
            errors.append(
                f"连线 {edge.id}: 端口类型不兼容（{edge.from_port} → {edge.to_port}）"
            )

    # 环
    try:
        topo_order(graph)
    except FlowError as exc:
        errors.append(str(exc))

    # 阶段唯一 / 顺序
    stages: dict[str, str] = {}
    for node in graph.nodes.values():
        if node.type != "stage":
            continue
        stage = str(node.params.get("stage") or "")
        if stage in stages:
            errors.append(f"阶段 {stage} 出现多个节点（{stages[stage]} 与 {node.id}）")
        stages[stage] = node.id
    for edge in graph.edges:
        from_stage = graph.stage_of(edge.from_node)
        to_stage = graph.stage_of(edge.to_node)
        if not from_stage or not to_stage or from_stage == to_stage:
            continue
        if STAGE_ORDER.index(to_stage) < STAGE_ORDER.index(from_stage):
            errors.append(f"阶段顺序倒置：{from_stage} → {to_stage}")
        elif STAGE_ORDER.index(to_stage) > STAGE_ORDER.index(from_stage) + 1:
            message = f"跳过阶段：{from_stage} → {to_stage}"
            if graph.settings.get("allow_skip_stages"):
                warnings.append(message)
            else:
                errors.append(message + "（如确需跳阶段，请在设置中开启 allow_skip_stages）")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def default_graph(project: str, graph_id: str = "flow-main") -> dict[str, Any]:
    """新建图的默认骨架：start + end（未连线，由用户在画布上连接）。"""
    now = _now()
    return {
        "contract_version": "0.1",
        "graph_id": graph_id,
        "name": "新建流程",
        "project": project,
        "created_at": now,
        "updated_at": now,
        "canvas": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
        "settings": {"auto_advance": False, "allow_skip_stages": False, "dry_run_first": True},
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "label": "开始",
                "position": {"x": 80, "y": 140},
                "params": {"project": project, "entry": "A"},
            },
            {
                "id": "end",
                "type": "end",
                "label": "结束",
                "position": {"x": 720, "y": 140},
                "params": {},
            },
        ],
        "edges": [],
    }


def _now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")
