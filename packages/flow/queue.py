"""批次队列（M14/M15）：把批量运行请求排入项目队列，按顺序执行并汇总失败通知。

队列文件：``00_project/workflows/queue.json``（文档契约 ``flow-queue`` v0.1）。
每个条目保存一次批量运行请求（图列表与参数），``run_queue`` 按 ``order``/创建顺序
处理 ``pending`` 条目，调用 :func:`flow.batch.run_batch` 生成批次记录，并把批次摘要、
失败图通知（``notification``）写回队列条目。

M15 起条目支持 ``scheduled_at``（计划执行时间，未到期不执行）、``canceled`` 状态
（取消待运行条目）与 ``order``（手动重排）；``flow queue daemon`` 可周期性执行到期条目。
``flow queue run --all-projects`` 可跨项目依次处理各项目队列（本地单用户）。
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import validate
from core_router.project import default_projects_root

from . import store
from .batch import (
    _check_parallel,
    _normalize_workers,
    _require_project,
    run_batch,
)
from .graph import FlowError
from .registry import NodeTypeRegistry

CONTRACT_VERSION = "0.1"
QUEUE_SCHEMA = "flow-queue.schema.json"
QUEUE_FILE_NAME = "queue.json"
QUEUE_ID_RE = re.compile(r"^q-[a-z0-9-]{4,80}$")
QUEUE_STATUSES = ("pending", "running", "succeeded", "failed", "canceled")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise FlowError("计划时间不能为空")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise FlowError(f"无法解析计划时间 {text!r}（请用 ISO 8601，如 2026-11-15T20:00）") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def normalize_schedule(value: str | None) -> str | None:
    """把用户输入的计划时间规范化为带时区的 ISO 字符串；None 表示立即。"""
    if value is None or not str(value).strip():
        return None
    return _parse_iso(value).isoformat(timespec="seconds")


def _is_due(entry: dict[str, Any], now: datetime | None = None) -> bool:
    scheduled = str(entry.get("scheduled_at") or "").strip()
    if not scheduled:
        return True
    try:
        when = _parse_iso(scheduled)
    except FlowError:
        return True
    return when <= (now or datetime.now().astimezone())


def _entry_order(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("order") or 0)
    except (TypeError, ValueError):
        return 0


def _sorted_pending(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [item for item in entries if item.get("status") == "pending"],
        key=lambda item: (_entry_order(item), str(item.get("created_at") or "")),
    )


def _next_order(entries: list[dict[str, Any]]) -> int:
    pending = _sorted_pending(entries)
    return (_entry_order(pending[-1]) + 1) if pending else 0


def new_queue_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"q-{stamp}-{secrets.token_hex(3)}"


def queue_path(project_root: str | Path) -> Path:
    return store.workflows_dir(Path(project_root)) / QUEUE_FILE_NAME


def _empty_doc(project: Path) -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION, "project": project.name, "entries": []}


def validate_queue(doc: dict[str, Any]) -> list[str]:
    return validate(doc, schema_name=QUEUE_SCHEMA)


def load_queue(project_root: str | Path) -> dict[str, Any]:
    """读取队列文档；文件不存在时返回空队列（不落盘）。"""
    project = _require_project(project_root)
    path = queue_path(project)
    if not path.is_file():
        return _empty_doc(project)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlowError(f"队列文件不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise FlowError("队列文件根节点必须是对象")
    problems = validate_queue(data)
    if problems:
        raise FlowError("队列文件不符合契约：" + "；".join(problems))
    return data


def write_queue(project_root: str | Path, doc: dict[str, Any]) -> Path:
    problems = validate_queue(doc)
    if problems:
        raise FlowError("队列文件不符合契约：" + "；".join(problems))
    return store.atomic_write_json(queue_path(Path(project_root)), doc)


def _save(project: Path, doc: dict[str, Any]) -> None:
    write_queue(project, doc)


def enqueue(
    project_root: str | Path,
    graph_ids: list[str] | None = None,
    *,
    all_graphs: bool = False,
    dry_run: bool | None = True,
    auto_confirm: bool = True,
    auto_retry: int = 0,
    fail_fast: bool = False,
    parallel: bool = False,
    workers: int = 2,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """把一次批量运行请求加入项目队列，返回新条目。"""
    project = _require_project(project_root)
    schedule = normalize_schedule(scheduled_at)
    if all_graphs:
        selected = [str(item["graph_id"]) for item in store.list_graphs(project)]
    else:
        selected = []
        for graph_id in graph_ids or []:
            graph_id = str(graph_id or "").strip()
            if graph_id and graph_id not in selected:
                selected.append(graph_id)
    if not selected:
        raise FlowError("没有可加入队列的流程图（请用 --graphs a,b 指定，或使用 --all）")
    effective_dry = True if dry_run is None else bool(dry_run)
    retry = max(0, min(3, int(auto_retry or 0)))
    worker_count = _normalize_workers(workers)
    _check_parallel(bool(parallel), effective_dry, bool(fail_fast))

    doc = load_queue(project)
    entry: dict[str, Any] = {
        "queue_id": new_queue_id(),
        "project": project.name,
        "graphs": selected,
        "dry_run": effective_dry,
        "auto_confirm": bool(auto_confirm),
        "auto_retry": retry,
        "fail_fast": bool(fail_fast),
        "parallel": bool(parallel),
        "workers": worker_count,
        "status": "pending",
        "order": _next_order(doc.get("entries") or []),
        "created_at": now_iso(),
    }
    if schedule:
        entry["scheduled_at"] = schedule
    doc["entries"].append(entry)
    _save(project, doc)
    return entry


def list_queue(
    project_root: str | Path,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """列出队列条目（新→旧）；可按状态过滤。"""
    project = _require_project(project_root)
    limit = max(1, min(200, int(limit)))
    if status and status not in QUEUE_STATUSES:
        raise FlowError(f"非法队列状态：{status!r}（可选 {'/'.join(QUEUE_STATUSES)}）")
    doc = load_queue(project)
    items = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    if status:
        items = [item for item in items if item.get("status") == status]
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[:limit]


def _aggregate_ran(ran: list[dict[str, Any]]) -> dict[str, int]:
    succeeded = sum(1 for item in ran if item.get("status") == "succeeded")
    failed = sum(1 for item in ran if item.get("status") == "failed")
    return {"total": len(ran), "succeeded": succeeded, "failed": failed}


def run_queue(
    project_root: str | Path,
    *,
    limit: int = 5,
    node_types: NodeTypeRegistry | None = None,
    sessions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 order/创建顺序执行队列中已到期的 pending 条目，返回本次结果与失败通知。"""
    project = _require_project(project_root)
    doc = load_queue(project)
    limit = max(1, min(50, int(limit)))
    entries = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    now = datetime.now().astimezone()
    pending_all = _sorted_pending(entries)
    pending = [item for item in pending_all if _is_due(item, now)][:limit]

    ran: list[dict[str, Any]] = []
    for entry in pending:
        if not isinstance(entry, dict):
            continue
        entry["status"] = "running"
        entry["started_at"] = now_iso()
        _save(project, doc)
        try:
            result = run_batch(
                project,
                list(entry.get("graphs") or []),
                dry_run=bool(entry.get("dry_run", True)),
                auto_confirm=bool(entry.get("auto_confirm", True)),
                auto_retry=int(entry.get("auto_retry") or 0),
                fail_fast=bool(entry.get("fail_fast")),
                limit=max(1, len(entry.get("graphs") or [])),
                parallel=bool(entry.get("parallel")),
                workers=int(entry.get("workers") or 2),
                node_types=node_types,
                sessions=sessions,
            )
            batch = result["batch"]
            summary = batch["summary"]
            entry["batch_id"] = batch["batch_id"]
            entry["finished_at"] = now_iso()
            entry["result"] = {
                "ok": bool(result["ok"]),
                "total": int(summary.get("total", 0)),
                "succeeded": int(summary.get("succeeded", 0)),
                "failed": int(summary.get("failed", 0)),
                "attempts": int(summary.get("attempts", 0)),
                "duration_ms": int(summary.get("duration_ms", 0)),
            }
            entry["status"] = "succeeded" if result["ok"] else "failed"
            entry.pop("error", None)
            if result["ok"]:
                entry.pop("notification", None)
            else:
                failed_graphs = [str(item.get("graph_id")) for item in batch.get("graphs") or [] if not item.get("ok")]
                entry["notification"] = {
                    "failed_graphs": failed_graphs,
                    "message": f"批次 {batch['batch_id']} 失败 {len(failed_graphs)} 个图：{', '.join(failed_graphs)}",
                }
        except FlowError as exc:
            entry["status"] = "failed"
            entry["finished_at"] = now_iso()
            entry["error"] = str(exc)
            entry["notification"] = {"failed_graphs": [], "message": f"队列条目 {entry['queue_id']} 运行失败：{exc}"}
        _save(project, doc)
        ran.append(
            {
                "queue_id": entry["queue_id"],
                "status": entry["status"],
                "batch_id": entry.get("batch_id"),
                "result": entry.get("result"),
                "notification": entry.get("notification"),
                "error": entry.get("error"),
            }
        )

    final_entries = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    remaining = sum(1 for item in final_entries if item.get("status") == "pending")
    scheduled = sum(
        1 for item in final_entries if item.get("status") == "pending" and not _is_due(item)
    )
    canceled = sum(1 for item in final_entries if item.get("status") == "canceled")
    return {
        "ok": all(item.get("status") != "failed" for item in ran),
        "project": str(project),
        "ran": ran,
        "summary": {
            **_aggregate_ran(ran),
            "pending": remaining,
            "scheduled": scheduled,
            "canceled": canceled,
        },
    }


def _find_entry(doc: dict[str, Any], queue_id: str) -> dict[str, Any]:
    target = str(queue_id or "").strip()
    if not target:
        raise FlowError("缺少队列条目 ID")
    for item in doc.get("entries") or []:
        if isinstance(item, dict) and item.get("queue_id") == target:
            return item
    raise FlowError(f"队列条目不存在：{target}")


def cancel_entry(project_root: str | Path, queue_id: str) -> dict[str, Any]:
    """取消一个待运行条目（已运行的条目不能取消）。"""
    project = _require_project(project_root)
    doc = load_queue(project)
    entry = _find_entry(doc, queue_id)
    if entry.get("status") != "pending":
        raise FlowError(f"只能取消待运行条目（当前 {entry.get('status')}）：{queue_id}")
    entry["status"] = "canceled"
    entry["finished_at"] = now_iso()
    entry["notification"] = {"failed_graphs": [], "message": f"队列条目 {queue_id} 已取消"}
    _save(project, doc)
    return entry


def move_entry(
    project_root: str | Path,
    queue_id: str,
    *,
    before: str | None = None,
    after: str | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    """重排待运行条目：把 queue_id 移到 before/after 之前或之后，或指定 0 基下标。"""
    if index is None and not before and not after:
        raise FlowError("请提供 --before / --after / --index 之一")
    if sum(item is not None for item in (index, before, after)) > 1:
        raise FlowError("--index / --before / --after 只能同时提供一个")
    project = _require_project(project_root)
    doc = load_queue(project)
    entry = _find_entry(doc, queue_id)
    if entry.get("status") != "pending":
        raise FlowError(f"只能移动待运行条目（当前 {entry.get('status')}）：{queue_id}")
    pending = _sorted_pending(doc.get("entries") or [])
    pending = [item for item in pending if item is not entry]
    if index is not None:
        position = int(index)
        if position < 0 or position > len(pending):
            raise FlowError(f"--index 超出范围（0–{len(pending)}）")
    else:
        anchor_id = before or after
        anchor_index = next(
            (pos for pos, item in enumerate(pending) if item.get("queue_id") == anchor_id),
            None,
        )
        if anchor_index is None:
            raise FlowError(f"目标条目不存在或不是待运行条目：{anchor_id}")
        position = anchor_index if before else anchor_index + 1
    pending.insert(position, entry)
    for pos, item in enumerate(pending):
        item["order"] = pos
    _save(project, doc)
    return {
        "queue_id": entry["queue_id"],
        "order": entry.get("order"),
        "pending": [
            {"queue_id": item["queue_id"], "order": item.get("order")} for item in pending
        ],
    }


def list_project_roots() -> list[Path]:
    """列出默认项目根下所有含 00_project/state.json 的项目（跨项目队列用）。"""
    root = default_projects_root()
    if not root.is_dir():
        return []
    projects: list[Path] = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and (path / "00_project" / "state.json").is_file():
            projects.append(path)
    return projects


__all__ = [
    "QUEUE_SCHEMA",
    "cancel_entry",
    "list_project_roots",
    "list_queue",
    "load_queue",
    "move_entry",
    "new_queue_id",
    "normalize_schedule",
    "queue_path",
    "run_queue",
    "validate_queue",
    "write_queue",
    "enqueue",
]
