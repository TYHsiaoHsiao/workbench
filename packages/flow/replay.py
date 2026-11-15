"""运行回放：把运行记录整理为时间线（每步耗时、关键输出、失败定位）。

`build_replay()` 是纯函数：输入 run 记录（可附当前图用于节点标题），输出结构化
回放数据，供 CLI `flow replay` 与 Web API `GET /api/runs/<id>/replay` 使用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _duration_ms(start: Any, end: Any) -> int | None:
    begin = _parse_ts(start)
    finish = _parse_ts(end)
    if begin is None or finish is None:
        return None
    return max(0, int((finish - begin).total_seconds() * 1000))


def _node_index(graph: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for node in (graph or {}).get("nodes") or []:
        if isinstance(node, dict) and node.get("id"):
            index[str(node["id"])] = node
    return index


def build_replay(run: dict[str, Any], graph: dict[str, Any] | None = None) -> dict[str, Any]:
    """把 run 记录整理为时间线；不修改输入。"""
    nodes = _node_index(graph)
    steps_out: list[dict[str, Any]] = []
    for position, step in enumerate(run.get("steps") or [], start=1):
        if not isinstance(step, dict):
            continue
        node_id = str(step.get("node_id") or "")
        node = nodes.get(node_id) or {}
        steps_out.append(
            {
                "index": position,
                "node_id": node_id,
                "label": str(node.get("label") or node_id),
                "node_type": str(node.get("type") or ""),
                "status": step.get("status"),
                "started_at": step.get("started_at"),
                "ended_at": step.get("ended_at"),
                "duration_ms": _duration_ms(step.get("started_at"), step.get("ended_at")),
                "outputs": list(step.get("outputs") or []),
                "logs": list(step.get("logs") or []),
                "error": step.get("error"),
                "state_before": step.get("state_before") or {},
                "state_after": step.get("state_after") or {},
            }
        )

    durations = [step["duration_ms"] for step in steps_out if step["duration_ms"] is not None]
    timed = [step for step in steps_out if step["duration_ms"] is not None]
    slowest = max(timed, key=lambda step: step["duration_ms"]) if timed else None
    failed = next((step for step in steps_out if step.get("status") == "failed"), None)

    return {
        "contract_version": "0.1",
        "run_id": run.get("run_id"),
        "graph_id": run.get("graph_id"),
        "project": run.get("project"),
        "status": run.get("status"),
        "mode": run.get("mode"),
        "dry_run": bool(run.get("dry_run")),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "total_duration_ms": _duration_ms(run.get("started_at"), run.get("finished_at")),
        "step_duration_ms": sum(durations),
        "steps": steps_out,
        "counts": {
            "total": len(steps_out),
            "succeeded": sum(1 for step in steps_out if step["status"] in {"succeeded", "planned"}),
            "failed": sum(1 for step in steps_out if step["status"] == "failed"),
            "skipped": sum(1 for step in steps_out if step["status"] == "skipped"),
            "waiting_confirmation": sum(
                1 for step in steps_out if step["status"] == "waiting_confirmation"
            ),
        },
        "slowest_node_id": slowest["node_id"] if slowest else None,
        "slowest_duration_ms": slowest["duration_ms"] if slowest else None,
        "failed_node_id": failed["node_id"] if failed else None,
        "failed_error": failed.get("error") if failed else None,
        "recovered_from": run.get("recovered_from"),
    }


def _fmt_ms(value: int | None) -> str:
    if value is None:
        return "-"
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000:.1f}s"


def format_replay_text(replay: dict[str, Any]) -> str:
    """把回放数据渲染为人类可读文本（CLI 用）。"""
    lines = [
        f"运行 {replay.get('run_id')} · {replay.get('status')}"
        + (" · dry-run" if replay.get("dry_run") else "")
    ]
    lines.append(
        f"总耗时: {_fmt_ms(replay.get('total_duration_ms'))}｜步骤耗时合计: "
        f"{_fmt_ms(replay.get('step_duration_ms'))}"
    )
    if replay.get("recovered_from"):
        lines.append(f"恢复自: {replay['recovered_from']}")
    if replay.get("failed_node_id"):
        lines.append(f"失败节点: {replay['failed_node_id']} · {replay.get('failed_error') or ''}")
    if replay.get("slowest_node_id"):
        lines.append(
            f"最慢节点: {replay['slowest_node_id']}（{_fmt_ms(replay.get('slowest_duration_ms'))}）"
        )
    lines.append("")
    flags = {
        "succeeded": "OK",
        "planned": "预演",
        "failed": "FAIL",
        "skipped": "跳过",
        "waiting_confirmation": "待确认",
    }
    for step in replay.get("steps") or []:
        flag = flags.get(str(step.get("status")), str(step.get("status")).upper())
        line = (
            f"[{_fmt_ms(step.get('duration_ms'))}] {step['index']:02d} "
            f"{step['node_id']} ({step['node_type']}) {flag}"
        )
        outputs = [str(item) for item in step.get("outputs") or []][:3]
        if outputs:
            line += " · " + "；".join(outputs)
        if step.get("error"):
            line += " · 错误: " + str(step["error"])
        lines.append(line)
    return "\n".join(lines)
