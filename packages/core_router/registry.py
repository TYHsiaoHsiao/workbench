"""路由核心：读取并校验阶段注册表，提供阶段查询与下游推导。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts import load_schema, validate

PACKAGES_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGES_ROOT.parent
DEFAULT_REGISTRY = REPO_ROOT / "content" / "stage-registry.json"


class RegistryError(ValueError):
    """注册表不合法（结构或引用）时抛出。"""


class Registry:
    """阶段注册表的内存视图，对外只读。"""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.contract_version: str = data["contract_version"]
        self.knowledge_bridge: dict[str, Any] = data["knowledge_bridge"]
        self._stages: dict[str, dict[str, Any]] = {
            stage["id"]: stage for stage in data["stages"]
        }

    @property
    def stages(self) -> list[dict[str, Any]]:
        return list(self._stages.values())

    def ids(self) -> list[str]:
        return list(self._stages.keys())

    def stage(self, stage_id: str | int) -> dict[str, Any]:
        key = f"{int(stage_id):02d}" if str(stage_id).isdigit() else str(stage_id)
        if key not in self._stages:
            raise KeyError(f"未知阶段: {stage_id!r}")
        return self._stages[key]

    def gates(self, stage_id: str | int) -> list[dict[str, Any]]:
        return self.stage(stage_id)["gates"]

    def output_paths(self, stage_id: str | int) -> list[str]:
        return self.stage(stage_id)["outputs"]

    def next_stage_id(self, stage_id: str | int) -> str:
        downstream = self.stage(stage_id)["downstream"]
        return downstream[0] if downstream else "done"


def _referential_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    stages = data.get("stages", [])
    ids = [stage.get("id") for stage in stages if isinstance(stage, dict)]
    if len(ids) != len(set(ids)):
        errors.append("$stages: 阶段 id 重复")
    known = set(ids)
    for stage in stages:
        sid = stage.get("id")
        for downstream in stage.get("downstream", []):
            if downstream not in known:
                errors.append(f"$stages.{sid}.downstream: 未知阶段 {downstream!r}")
    return errors


def validate_registry(path: str | Path | None = None) -> list[str]:
    """校验注册表文件；返回错误列表（空表示合法）。"""
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY
    try:
        with registry_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{registry_path}: 无法读取注册表: {exc}"]
    errors = validate(data, schema_name="stage-registry")
    errors.extend(_referential_errors(data))
    return errors


def load_registry(path: str | Path | None = None) -> Registry:
    """加载并校验注册表；不合法时抛出 RegistryError。"""
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY
    errors = validate_registry(registry_path)
    if errors:
        raise RegistryError("注册表校验失败:\n" + "\n".join(f"- {err}" for err in errors))
    with registry_path.open("r", encoding="utf-8") as fh:
        return Registry(json.load(fh))
