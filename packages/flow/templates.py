"""流程模板：从 content/flow-templates.json 读取预置流程图并实例化到项目。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from contracts import validate

TEMPLATES_SCHEMA = "flow-templates.schema.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATES = REPO_ROOT / "content" / "flow-templates.json"


class TemplateError(Exception):
    """模板加载 / 实例化错误。"""


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_templates(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path else DEFAULT_TEMPLATES
    if not target.is_file():
        raise TemplateError(f"模板文件不存在: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateError(f"模板文件不是合法 JSON: {exc}") from exc
    errors = validate(data, schema_name=TEMPLATES_SCHEMA)
    if errors:
        raise TemplateError("模板文件未通过契约校验: " + "；".join(errors))
    templates = data.get("templates") or []
    seen: set[str] = set()
    for item in templates:
        tid = item.get("template_id")
        if tid in seen:
            raise TemplateError(f"模板 id 重复: {tid}")
        seen.add(tid)
    return templates


def get_template(template_id: str, path: str | Path | None = None) -> dict[str, Any]:
    for item in load_templates(path):
        if item.get("template_id") == template_id:
            return item
    raise TemplateError(f"模板不存在: {template_id}")


def instantiate(
    template: dict[str, Any],
    project: str,
    graph_id: str = "flow-main",
    name: str | None = None,
) -> dict[str, Any]:
    """把模板 graph 实例化为指定项目的新流程图（深拷贝，不修改模板本体）。"""
    graph = copy.deepcopy(template.get("graph") or {})
    if not graph:
        raise TemplateError("模板缺少 graph")
    stamp = _now()
    graph["graph_id"] = graph_id
    graph["project"] = project
    graph["name"] = name or template.get("name") or graph_id
    graph["created_at"] = stamp
    graph["updated_at"] = stamp
    for node in graph.get("nodes") or []:
        if node.get("type") == "start":
            params = dict(node.get("params") or {})
            params["project"] = project
            node["params"] = params
    return graph


def instantiate_template(
    template_id: str,
    project: str,
    graph_id: str = "flow-main",
    name: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    template = get_template(template_id, path)
    return instantiate(template, project, graph_id=graph_id, name=name)


__all__ = ["DEFAULT_TEMPLATES", "TEMPLATES_SCHEMA", "TemplateError", "get_template", "instantiate", "instantiate_template", "load_templates"]
