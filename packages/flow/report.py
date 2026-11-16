"""批次趋势报表（M33/M35）：把最近批次记录汇总为 Markdown/CSV/HTML 文本。

零依赖，只读取 ``00_project/workflows/batches/*.json`` 的摘要，不写任何文件。
HTML 为自包含单文件（内联 CSS，无外部资源），可直接下载或发送。
"""
from __future__ import annotations

import csv
import html
import io
from pathlib import Path
from typing import Any

REPORT_FORMATS = ("md", "csv", "html")
COLS = ("batch_id", "started_at", "status", "total", "succeeded", "failed", "duration_ms", "auto_retry")


def _require_project(project_root: str | Path) -> Path:
    from .batch import _require_project as _impl

    return _impl(project_root)


def _rate(part: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


def _html_report(project: Path, batches: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    """生成自包含 HTML 报表（内联 CSS，无外链资源）。"""

    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else ""), quote=True)

    rows: list[str] = []
    bars: list[str] = []
    max_total = max([int(item.get("total") or 0) for item in batches] + [1])
    for item in batches:
        status = str(item.get("status") or "")
        ok = status == "succeeded"
        total = int(item.get("total") or 0)
        failed = int(item.get("failed") or 0)
        succeeded = int(item.get("succeeded") or 0)
        width = max(4, int(total / max_total * 100)) if total else 4
        bars.append(
            f'<div class="bar-row"><span class="bar-label">{esc(item.get("batch_id", ""))}</span>'
            f'<span class="bar"><span class="bar-fill {"ok" if ok else "bad"}" style="width:{width}%"></span></span>'
            f'<span class="bar-meta">成功 {succeeded} · 失败 {failed}</span></div>'
        )
        rows.append(
            "<tr>"
            f"<td>{esc(item.get('batch_id', ''))}</td>"
            f"<td>{esc(item.get('started_at', ''))}</td>"
            f'<td class="st-{"ok" if ok else "bad"}">{esc(status)}</td>'
            f"<td>{total}</td><td>{succeeded}</td><td>{failed}</td>"
            f"<td>{int(item.get('duration_ms') or 0)}</td>"
            f"<td>{int(item.get('auto_retry') or 0)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="8">（暂无批次）</td></tr>')
    if not bars:
        bars.append('<p class="muted">（暂无趋势数据）</p>')
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>批次趋势报表 · {esc(project.name)}</title>
<style>
  body {{ margin: 0; padding: 24px; background: #0f172a; color: #e2e8f0; font: 14px/1.5 system-ui, sans-serif; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .muted {{ color: #94a3b8; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; min-width: 140px; }}
  .card .num {{ font-size: 22px; font-weight: 600; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; }}
  .bar-label {{ width: 240px; font-family: ui-monospace, monospace; font-size: 12px; color: #cbd5e1; }}
  .bar {{ flex: 1; height: 10px; background: #1e293b; border-radius: 5px; overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; }}
  .bar-fill.ok {{ background: #22c55e; }}
  .bar-fill.bad {{ background: #ef4444; }}
  .bar-meta {{ width: 130px; text-align: right; font-size: 12px; color: #94a3b8; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 18px; font-size: 13px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #1e293b; }}
  th {{ color: #94a3b8; font-weight: 500; }}
  .st-ok {{ color: #22c55e; }}
  .st-bad {{ color: #ef4444; }}
</style>
</head>
<body>
<h1>批次趋势报表（最近 {len(batches)} 次）</h1>
<div class="muted">项目：{esc(project)}</div>
<div class="cards">
  <div class="card"><div class="num">{summary['batches']}</div><div class="muted">批次</div></div>
  <div class="card"><div class="num">{summary['total']}</div><div class="muted">图运行</div></div>
  <div class="card"><div class="num">{summary['success_rate']}</div><div class="muted">成功率</div></div>
  <div class="card"><div class="num">{summary['avg_duration_ms']} ms</div><div class="muted">平均批次耗时</div></div>
</div>
<h2>成功/失败趋势</h2>
{"".join(bars)}
<h2>明细</h2>
<table>
<thead><tr><th>批次</th><th>开始时间</th><th>状态</th><th>图数</th><th>成功</th><th>失败</th><th>耗时(ms)</th><th>重试</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
<p class="muted">由 workbench batch-report 生成（M35）。</p>
</body>
</html>
"""


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
    elif fmt == "html":
        text = _html_report(project, batches, summary)
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
