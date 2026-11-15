"""节点类型注册表：读取 content/flow-node-types.json，提供参数校验与端口信息。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contracts import validate

from .graph import FlowError

NODE_TYPES_SCHEMA = "flow-node-types.schema.json"
CONTENT_TYPES_FILE = Path(__file__).resolve().parents[2] / "content" / "flow-node-types.json"


@dataclass(frozen=True)
class NodeType:
    type: str
    label: str
    category: str
    description: str
    ports_in: tuple[str, ...]
    ports_out: tuple[str, ...]
    params_schema: dict[str, Any]
    executor: str
    constraints: tuple[str, ...] = field(default_factory=tuple)
    parallel_safe: bool = False

    def default_params(self) -> dict[str, Any]:
        """按 params_schema 生成默认参数（enum 取首项、boolean=False、string=""）。"""
        schema = self.params_schema or {}
        properties = schema.get("properties") or {}
        params: dict[str, Any] = {}
        for name, spec in properties.items():
            if not isinstance(spec, dict):
                continue
            if "default" in spec:
                params[name] = spec["default"]
            elif isinstance(spec.get("enum"), list) and spec["enum"]:
                params[name] = spec["enum"][0]
            elif spec.get("type") == "boolean":
                params[name] = False
            elif spec.get("type") == "number" or spec.get("type") == "integer":
                params[name] = 0
            else:
                params[name] = ""
        return params


class NodeTypeRegistry:
    def __init__(self, data: dict[str, Any], path: Path | None = None) -> None:
        self.path = path
        self.contract_version = str(data.get("contract_version") or "")
        self._types: dict[str, NodeType] = {}
        for item in data.get("types") or []:
            node_type = NodeType(
                type=str(item["type"]),
                label=str(item.get("label") or item["type"]),
                category=str(item.get("category") or "其他"),
                description=str(item.get("description") or ""),
                ports_in=tuple(item.get("ports", {}).get("in") or ()),
                ports_out=tuple(item.get("ports", {}).get("out") or ()),
                params_schema=dict(item.get("params_schema") or {}),
                executor=str(item.get("executor") or item["type"]),
                constraints=tuple(item.get("constraints") or ()),
                parallel_safe=bool(item.get("parallel_safe", False)),
            )
            self._types[node_type.type] = node_type

    # -- 查询 ---------------------------------------------------------
    def get(self, type_name: str) -> NodeType | None:
        return self._types.get(type_name)

    def require(self, type_name: str) -> NodeType:
        node_type = self.get(type_name)
        if node_type is None:
            raise FlowError(f"节点类型未注册: {type_name}")
        return node_type

    def types(self) -> list[NodeType]:
        return list(self._types.values())

    def __len__(self) -> int:
        return len(self._types)

    def categories(self) -> list[str]:
        seen: list[str] = []
        for node_type in self._types.values():
            if node_type.category not in seen:
                seen.append(node_type.category)
        return seen

    # -- 校验 ---------------------------------------------------------
    def validate_params(self, type_name: str, params: dict[str, Any]) -> list[str]:
        node_type = self.get(type_name)
        if node_type is None:
            return [f"节点类型未注册: {type_name}"]
        schema = node_type.params_schema or {"type": "object"}
        return list(validate(params, schema=schema))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "types": [
                {
                    "type": node_type.type,
                    "label": node_type.label,
                    "category": node_type.category,
                    "description": node_type.description,
                    "ports": {"in": list(node_type.ports_in), "out": list(node_type.ports_out)},
                    "params_schema": node_type.params_schema,
                    "executor": node_type.executor,
                    "constraints": list(node_type.constraints),
                    "parallel_safe": node_type.parallel_safe,
                }
                for node_type in self._types.values()
            ],
        }


def parse_node_types(data: dict[str, Any], path: Path | None = None) -> NodeTypeRegistry:
    errors = validate(data, schema_name=NODE_TYPES_SCHEMA)
    if errors:
        raise FlowError("节点类型注册表校验失败: " + "; ".join(errors))
    return NodeTypeRegistry(data, path=path)


def load_node_types(path: Path | str | None = None) -> NodeTypeRegistry:
    target = Path(path) if path else CONTENT_TYPES_FILE
    if not target.is_file():
        raise FlowError(f"节点类型注册表不存在: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"节点类型注册表读取失败: {exc}") from exc
    return parse_node_types(data, path=target)
