"""门禁引擎：按注册表与条件门禁阻止跳过阶段。

门禁状态存放于项目状态文件 `00_project/state.json` 的 `gates` 数组：
    {"id": "positioning_menu", "stage": "01", "status": "passed", "note": "", "updated_at": "..."}

硬门禁（hard）必须 passed 才能推进；软门禁（soft）可显式 waived。
所有写入函数只修改传入的 state 字典，持久化由调用方负责。
"""
from __future__ import annotations

import datetime
from typing import Any

from core_router.registry import Registry, load_registry
from core_router.state import bump_version, validate_state

GATE_STATUSES = ("pending", "passed", "failed", "waived")
DONE = "done"

# 不在注册表内、按项目情况追加的条件门禁。
CONDITIONAL_GATES: dict[str, dict[str, str]] = {
    "screenplay_intake": {
        "type": "hard",
        "description": "B 入口：完整剧本接管检查报告已展示并获确认",
    },
    "knowledge_card_confirm": {
        "type": "hard",
        "description": "知识卡已完整展示并获用户确认（知识桥非 off 时必需）",
    },
}


class GateError(ValueError):
    """门禁操作不合法（未知门禁、硬门禁不可豁免、推进被阻止）时抛出。"""


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _gate_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for gate in state.get("gates", []) or []:
        if isinstance(gate, dict) and gate.get("id"):
            index[gate["id"]] = gate
    return index


def conditional_gate_ids(state: dict[str, Any], stage: str) -> list[str]:
    """按项目入口/知识桥状态计算条件门禁。"""
    ids: list[str] = []
    if stage == "01" and state.get("entry") == "B":
        ids.append("screenplay_intake")
    bridge = state.get("knowledge_bridge") or {}
    if stage == "05" and bridge.get("status", "off") != "off":
        ids.append("knowledge_card_confirm")
    return ids


def required_gates(state: dict[str, Any], stage: str,
                   registry: Registry | None = None) -> list[dict[str, Any]]:
    """当前阶段需要的全部门禁（注册表门禁 + 条件门禁）。"""
    registry = registry or load_registry()
    gates = [dict(gate, type=gate.get("type", "hard")) for gate in registry.gates(stage)]
    known = {gate["id"] for gate in gates}
    for gate_id in conditional_gate_ids(state, stage):
        if gate_id not in known:
            gates.append({"id": gate_id, **CONDITIONAL_GATES[gate_id]})
    return gates


def ensure_stage_gates(state: dict[str, Any], stage: str,
                       registry: Registry | None = None) -> list[str]:
    """补齐当前阶段缺失的门禁条目，返回新增的 id 列表。"""
    registry = registry or load_registry()
    if stage == DONE:
        return []
    required = required_gates(state, stage, registry)
    existing = _gate_index(state)
    added: list[str] = []
    state.setdefault("gates", [])
    for gate in required:
        gate_id = gate["id"]
        entry = existing.get(gate_id)
        if entry is None:
            state["gates"].append(
                {"id": gate_id, "stage": stage, "status": "pending",
                 "note": "", "updated_at": _now()}
            )
            added.append(gate_id)
        else:
            entry.setdefault("stage", stage)
    return added


def gate_detail(state: dict[str, Any], stage: str | None = None,
                registry: Registry | None = None) -> list[dict[str, Any]]:
    """当前阶段门禁的完整视图。"""
    stage = stage or state.get("stage", "01")
    if stage == DONE:
        return []
    registry = registry or load_registry()
    index = _gate_index(state)
    detail: list[dict[str, Any]] = []
    for required in required_gates(state, stage, registry):
        entry = index.get(required["id"], {})
        detail.append(
            {
                "id": required["id"],
                "type": required.get("type", "hard"),
                "description": required.get("description", ""),
                "status": entry.get("status", "pending"),
                "note": entry.get("note", ""),
            }
        )
    return detail


def pending_gates(state: dict[str, Any], stage: str | None = None,
                  registry: Registry | None = None) -> list[str]:
    """未通过的门禁 id（含缺失条目，按 pending 计）。"""
    stage = stage or state.get("stage", "01")
    return [item["id"] for item in gate_detail(state, stage, registry)
            if item["status"] != "passed"]


def can_advance(state: dict[str, Any], stage: str | None = None,
                registry: Registry | None = None) -> tuple[bool, list[str]]:
    """是否可以推进到下一阶段；返回 (是否可推进, 阻止原因)。"""
    stage = stage or state.get("stage", "01")
    if stage == DONE:
        return False, ["项目已完成全部阶段"]
    registry = registry or load_registry()
    reasons: list[str] = []
    for item in gate_detail(state, stage, registry):
        if item["status"] == "passed":
            continue
        if item["status"] == "waived":
            if item["type"] == "hard":
                reasons.append(f"硬门禁不可豁免: {item['id']}")
            continue
        reasons.append(f"门禁未通过: {item['id']}({item['status']})")
    return not reasons, reasons


def _find_gate(state: dict[str, Any], gate_id: str) -> dict[str, Any]:
    gate = _gate_index(state).get(gate_id)
    if gate is None:
        raise GateError(f"未知门禁: {gate_id}")
    return gate


def _require_gate(state: dict[str, Any], gate_id: str, registry: Registry | None = None) -> dict[str, Any]:
    gate = _gate_index(state).get(gate_id)
    if gate is not None:
        return gate
    stage = state.get("stage", "01")
    ensure_stage_gates(state, stage, registry)
    return _find_gate(state, gate_id)


def pass_gate(state: dict[str, Any], gate_id: str, note: str = "",
              registry: Registry | None = None) -> dict[str, Any]:
    gate = _require_gate(state, gate_id, registry)
    gate["status"] = "passed"
    gate["note"] = note
    gate["updated_at"] = _now()
    return gate


def fail_gate(state: dict[str, Any], gate_id: str, note: str = "",
              registry: Registry | None = None) -> dict[str, Any]:
    gate = _require_gate(state, gate_id, registry)
    gate["status"] = "failed"
    gate["note"] = note
    gate["updated_at"] = _now()
    return gate


def gate_type(state: dict[str, Any], gate_id: str,
              registry: Registry | None = None) -> str:
    registry = registry or load_registry()
    stage = state.get("stage", "01")
    for item in required_gates(state, stage, registry):
        if item["id"] == gate_id:
            return item.get("type", "hard")
    raise GateError(f"未知门禁: {gate_id}")


def waive_gate(state: dict[str, Any], gate_id: str, note: str = "",
               registry: Registry | None = None) -> dict[str, Any]:
    """豁免软门禁；硬门禁必须真实通过，不可绕过。"""
    if gate_type(state, gate_id, registry) == "hard":
        raise GateError(f"硬门禁不可豁免: {gate_id}")
    gate = _require_gate(state, gate_id, registry)
    gate["status"] = "waived"
    gate["note"] = note
    gate["updated_at"] = _now()
    return gate


def advance(state: dict[str, Any], registry: Registry | None = None) -> str:
    """推进到下一阶段；门禁未全部通过时抛 GateError。"""
    registry = registry or load_registry()
    stage = state.get("stage", "01")
    ok, reasons = can_advance(state, stage, registry)
    if not ok:
        raise GateError("门禁未全部通过，不能推进: " + "; ".join(reasons))
    next_stage = registry.next_stage_id(stage)
    state["stage"] = next_stage
    state["version"] = bump_version(state["version"])
    state.setdefault("revision_log", []).append(
        {"at": _now(), "action": "advance", "stage": next_stage,
         "note": f"{stage} -> {next_stage}"}
    )
    if next_stage == DONE:
        state["next_action"] = "全部阶段已完成；可导出成片或开始新项目"
    else:
        ensure_stage_gates(state, next_stage, registry)
        state["next_action"] = f"进入阶段 {next_stage}：{registry.stage(next_stage)['name']}"
    errors = validate_state(state)
    if errors:
        raise GateError("推进后状态不合法: " + "; ".join(errors))
    return next_stage


def mark_downstream_stale(state: dict[str, Any], stage: str | None = None,
                          registry: Registry | None = None) -> list[str]:
    """上游修订后，把当前阶段之后的全部阶段标记为可能过期（按注册表顺序）。"""
    registry = registry or load_registry()
    stage = stage or state.get("stage", "01")
    order = registry.ids()
    if stage not in order:
        return []
    stale = order[order.index(stage) + 1:]
    merged = sorted(set(state.get("stale_downstream", [])) | set(stale))
    state["stale_downstream"] = merged
    state.setdefault("revision_log", []).append(
        {"at": _now(), "action": "revise_upstream", "stage": stage,
         "note": "标记下游可能过期: " + ", ".join(stale)}
    )
    return stale
