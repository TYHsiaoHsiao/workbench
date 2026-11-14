"""项目状态：默认状态构造、schema 校验与版本递增工具。"""
from __future__ import annotations

from typing import Any

from contracts import validate

STATE_SCHEMA = "state.schema.json"


def default_state(project: str, entry: str = "A", mode: str = "full",
                  stage: str = "01") -> dict[str, Any]:
    """构造一份符合 state.schema.json 的新项目状态。"""
    if not project:
        raise ValueError("project 不能为空")
    return {
        "contract_version": "1.0",
        "project": project,
        "entry": entry,
        "mode": mode,
        "stage": stage,
        "version": "v01",
        "authoritative_inputs": [],
        "gates": [],
        "references": [],
        "style_profile": "",
        "stale_downstream": [],
        "next_action": "确认项目入口与定位后，进入当前阶段",
    }


def validate_state(state: dict[str, Any]) -> list[str]:
    return validate(state, schema_name=STATE_SCHEMA)


def bump_version(version: str) -> str:
    """v01 -> v02；格式非法时抛 ValueError。"""
    if not isinstance(version, str) or len(version) != 3 or version[0] != "v" or not version[1:].isdigit():
        raise ValueError(f"版本号格式应为 vNN，实际 {version!r}")
    return f"v{int(version[1:]) + 1:02d}"
