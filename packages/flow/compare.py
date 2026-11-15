"""两次运行对比（M6）。

按节点对齐两次运行记录，输出状态变化、耗时差与整体回归/改善摘要。
纯派生数据，不读取也不修改 ``state.json``。
"""
from __future__ import annotations

from typing import Any

from .replay import _duration_ms


def _step_index(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for step in run.get("steps") or []:
        node_id = step.get("node_id")
        if node_id:
            index[str(node_id)] = step
    return index


def _stage_of(run: dict[str, Any]) -> str | None:
    steps = run.get("steps") or []
    if steps:
        before = steps[0].get("state_before") or {}
        return before.get("stage")
    snapshot = run.get("state_snapshot_before") or {}
    return snapshot.get("stage")


def _delta_slow(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return b - a


def compare_runs(base: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """对比 base（较早）与 target（较新）两次运行。"""
    base_index = _step_index(base)
    target_index = _step_index(target)
    node_ids: list[str] = list(dict.fromkeys([*base_index, *target_index]))

    changes: list[dict[str, Any]] = []
    counts = {"same": 0, "status_changed": 0, "slower": 0, "faster": 0, "added": 0, "removed": 0}
    base_total = target_total = 0
    for node_id in node_ids:
        a = base_index.get(node_id)
        b = target_index.get(node_id)
        dur_a = _duration_ms(a.get("started_at"), a.get("ended_at")) if a else None
        dur_b = _duration_ms(b.get("started_at"), b.get("ended_at")) if b else None
        if a is None:
            change = "added"
            counts["added"] += 1
        elif b is None:
            change = "removed"
            counts["removed"] += 1
        elif str(a.get("status")) != str(b.get("status")):
            change = "status_changed"
            counts["status_changed"] += 1
        else:
            delta = _delta_slow(dur_a, dur_b)
            if delta is None or delta == 0:
                change = "same"
                counts["same"] += 1
            elif delta > 0:
                change = "slower"
                counts["slower"] += 1
            else:
                change = "faster"
                counts["faster"] += 1
        if dur_a is not None:
            base_total += dur_a
        if dur_b is not None:
            target_total += dur_b
        changes.append(
            {
                "node_id": node_id,
                "change": change,
                "status": b.get("status") if b else None,
                "base_status": a.get("status") if a else None,
                "target_status": b.get("status") if b else None,
                "duration_base_ms": dur_a,
                "duration_target_ms": dur_b,
                "delta_ms": _delta_slow(dur_a, dur_b),
            }
        )

    regressed = counts["status_changed"] + counts["slower"] + counts["added"]
    summary = {
        **counts,
        "base_steps": len(base_index),
        "target_steps": len(target_index),
        "base_total_ms": base_total,
        "target_total_ms": target_total,
        "total_delta_ms": target_total - base_total,
        "regressed": regressed,
        "improved": counts["faster"] + counts["removed"],
    }
    return {
        "ok": True,
        "base_run": base.get("run_id"),
        "target_run": target.get("run_id"),
        "base_status": base.get("status"),
        "target_status": target.get("status"),
        "base_mode": base.get("mode"),
        "target_mode": target.get("mode"),
        "base_dry_run": bool(base.get("dry_run")),
        "target_dry_run": bool(target.get("dry_run")),
        "stage_before": _stage_of(base),
        "stage_after": _stage_of(target),
        "node_changes": changes,
        "summary": summary,
    }


def format_compare_text(diff: dict[str, Any]) -> str:
    """把对比结果格式化为文本。"""
    s = diff.get("summary") or {}
    lines = [
        f"运行对比：{diff.get('base_run')}  →  {diff.get('target_run')}",
        f"状态：{diff.get('base_status')} → {diff.get('target_status')}"
        f" · 模式 {diff.get('base_mode')} → {diff.get('target_mode')}"
        f" · dry-run {diff.get('base_dry_run')} → {diff.get('target_dry_run')}",
        f"阶段：{diff.get('stage_before')} → {diff.get('stage_after')}",
        f"步骤：{s.get('base_steps')} → {s.get('target_steps')}"
        f" · 总耗时 {s.get('base_total_ms')}ms → {s.get('target_total_ms')}ms"
        f"（差 {s.get('total_delta_ms')}ms）",
        f"变化：same {s.get('same')} · status {s.get('status_changed')}"
        f" · slower {s.get('slower')} · faster {s.get('faster')}"
        f" · added {s.get('added')} · removed {s.get('removed')}",
    ]
    for item in diff.get("node_changes") or []:
        if item.get("change") == "same":
            continue
        lines.append(
            f"- {item.get('node_id')}: {item.get('change')}"
            f"（{item.get('base_status')} → {item.get('target_status')}，"
            f"{item.get('duration_base_ms')}ms → {item.get('duration_target_ms')}ms）"
        )
    return "\n".join(lines)
