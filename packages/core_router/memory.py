"""跨阶段参考记忆 v2 读取与阶段筛选。

单一事实来源是项目内 ``00_project/reference-memory.json``（契约校验）；
``reference-memory.md`` 只是给人看的视图，不参与运行时判断。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts import validate

from .project import REFERENCE_MEMORY_JSON, ProjectError

STAGE_SCOPES: dict[str, str] = {
    "01": "story_01_05",
    "02": "story_01_05",
    "03": "story_01_05",
    "04": "story_01_05",
    "05": "story_01_05",
    "06": "image_06",
    "07": "performance_07",
    "08": "camera_08",
}


class MemoryError(Exception):
    """参考记忆缺失或不符合契约。"""


def scope_for_stage(stage: str) -> str:
    scope = STAGE_SCOPES.get(str(stage))
    if scope is None:
        raise MemoryError(f"未知阶段：{stage}（应为 01-08）")
    return scope


def memory_path(project_root: str | Path) -> Path:
    return Path(project_root) / "00_project" / REFERENCE_MEMORY_JSON


def load_memory(project_root: str | Path) -> dict[str, Any]:
    path = memory_path(project_root)
    if not path.is_file():
        raise MemoryError(f"参考记忆不存在：{path}（可先运行 workbench.py init 或 migrate）")
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MemoryError(f"参考记忆不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise MemoryError("参考记忆根节点必须是对象")
    problems = validate(data, schema_name="reference-memory.schema.json")
    if problems:
        raise MemoryError("参考记忆不符合契约：" + "；".join(problems))
    return data


def entries_for_stage(
    memory: dict[str, Any], stage: str, include_disabled: bool = False
) -> list[dict[str, Any]]:
    """返回适用当前阶段且状态为 enabled 的条目（full 视为全阶段适用）。"""
    scope = scope_for_stage(stage)
    result = []
    for entry in memory.get("entries") or []:
        status = entry.get("status")
        if not include_disabled and status != "enabled":
            continue
        scopes = entry.get("scope") or []
        if scope in scopes or "full" in scopes:
            result.append(entry)
    return result


def summarize(memory: dict[str, Any]) -> dict[str, Any]:
    entries = list(memory.get("entries") or [])
    enabled = [e for e in entries if e.get("status") == "enabled"]
    by_scope: dict[str, int] = {}
    for entry in enabled:
        for scope in entry.get("scope") or []:
            by_scope[scope] = by_scope.get(scope, 0) + 1
    return {
        "total": len(entries),
        "enabled": len(enabled),
        "disabled": len([e for e in entries if e.get("status") == "disabled"]),
        "removed": len([e for e in entries if e.get("status") == "removed"]),
        "by_scope": by_scope,
    }


__all__ = [
    "MemoryError",
    "STAGE_SCOPES",
    "entries_for_stage",
    "load_memory",
    "memory_path",
    "scope_for_stage",
    "summarize",
]
