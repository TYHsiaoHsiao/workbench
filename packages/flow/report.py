"""批次趋势报表（M33）：把最近批次记录汇总为 Markdown/CSV 文本。

零依赖，只读取 ``00_project/workflows/batches/*.json`` 的摘要，不写任何文件。
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

REPORT_FORMATS = ("md", "csv")
COLS = ("batch_id", "started_at", "status", "total", "succeeded", "failed", "duration_ms", "auto_retry")


def _require_project(project_root: str | Path) -> Path:
    from .batch import _require_project as _impl

    return _impl(project_root)


def _rate(part: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


def batch_report(
    project_root: str | Path,
    *,
    limit: int = 20,
    fmt: str = "md",
) -> dict[str, Any]:
    """返回最近 ``limit`` 个批次的报表文本与统计（不写文件）。"""
    if fmt not in REPORT_FORMATS:
        raise ValueError(f"未知报表格式: {fmt}（可选 {'/'.join(REPORT_FORMATS)}）")
    from .batch import list_batches

    project = _require_project(project_root)
    batches = list_batches(project, limit=max(1, min(200, int(limit))))
    total = sum(int(item.get("total") or 0) for item in batches)
    succeeded = sum(int(item.get("succeeded") or 0) for item in batches)
    failed = sum(int(item.get("failed") or 0) for item in batches)
    durations = [int(item.get("duration_ms") or 0) for item in batches]
    avg_duration = int(sum(durations) / len(durations)) if durations else 0
    summary = {
        "batches": len(batches),
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": _rate(succeeded, total),
        "avg_duration_ms": avg_duration,
    }
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=COLS)
        writer.writeheader()
        for item in batches:
            writer.writerow({key: item.get(key, "") for key in COLS})
        text = buffer.getvalue()
    else:
        head = f"# 批次趋势报表（最近 {len(batches)} 次）"
        lines = [head, "", f"- 批次：{summary['batches']}；图运行：{total}；成功 {succeeded} / 失败 {failed}（成功率 {summary['success_rate']}）", f"- 平均批次耗时：{avg_duration} ms", ""]
        lines.append("| 批次 | 开始时间 | 状态 | 图数 | 成功 | 失败 | 耗时(ms) |")
        lines.append("|---|---|---|---|---|---|---|")
        for item in batches:
            lines.append(
                f"| {item.get('batch_id', '')} | {item.get('started_at', '')} | {item.get('status', '')} "
                f"| {item.get('total', 0)} | {item.get('succeeded', 0)} | {item.get('failed', 0)} | {item.get('duration_ms', 0)} |"
            )
        if not batches:
            lines.append("| （暂无批次） |  |  |  |  |  |  |")
        text = "\n".join(lines) + "\n"
    return {
        "ok": True,
        "project": str(project),
        "format": fmt,
        "summary": summary,
        "text": text,
    }


__all__ = ["COLS", "REPORT_FORMATS", "batch_report"]
