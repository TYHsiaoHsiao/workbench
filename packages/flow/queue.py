"""批次队列（M14/M15）：把批量运行请求排入项目队列，按顺序执行并汇总失败通知。

队列文件：``00_project/workflows/queue.json``（文档契约 ``flow-queue`` v0.1）。
每个条目保存一次批量运行请求（图列表与参数），``run_queue`` 按 ``order``/创建顺序
处理 ``pending`` 条目，调用 :func:`flow.batch.run_batch` 生成批次记录，并把批次摘要、
失败图通知（``notification``）写回队列条目。

M15 起条目支持 ``scheduled_at``（计划执行时间，未到期不执行）、``canceled`` 状态
（取消待运行条目）与 ``order``（手动重排）；``flow queue daemon`` 可周期性执行到期条目。
``flow queue run --all-projects`` 可跨项目依次处理各项目队列（本地单用户）。

M16 起支持失败重试策略与通知外送：``retry_entry``/``--retry-failed`` 把失败条目重置为
pending（``attempts`` 累加），``list_notifications``/``notify_cmd`` 记录或外送失败通知
（``00_project/workflows/queue-notifications.jsonl``）。
"""
from __future__ import annotations

import json
import re
import secrets
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import validate
from core_router.project import default_projects_root

from .notify import notify_webhook as _notify_webhook

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
NOTIFY_LOG_NAME = "queue-notifications.jsonl"
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


def _entry_attempts(entry: dict[str, Any]) -> int:
    try:
        return max(0, int(entry.get("attempts") or 0))
    except (TypeError, ValueError):
        return 0


def _reset_to_pending(entry: dict[str, Any]) -> None:
    """把失败条目重置为待运行，并累加重试次数、清理上次运行结果。"""
    entry["attempts"] = _entry_attempts(entry) + 1
    entry["status"] = "pending"
    for key in ("batch_id", "result", "notification", "error", "finished_at", "started_at"):
        entry.pop(key, None)


def new_queue_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"q-{stamp}-{secrets.token_hex(3)}"


def queue_path(project_root: str | Path) -> Path:
    return store.workflows_dir(Path(project_root)) / QUEUE_FILE_NAME


def notify_path(project_root: str | Path) -> Path:
    """失败通知日志路径：``00_project/workflows/queue-notifications.jsonl``。"""
    return store.workflows_dir(Path(project_root)) / NOTIFY_LOG_NAME


def _append_notification(project: Path, payload: dict[str, Any]) -> None:
    """把一条失败通知追加到 JSONL 通知日志（写失败不影响队列执行）。"""
    path = notify_path(project)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


def list_notifications(project_root: str | Path, *, limit: int = 20) -> list[dict[str, Any]]:
    """读取最近的通知记录（新→旧），供 CLI/Web 查看外送记录。"""
    project = _require_project(project_root)
    path = notify_path(project)
    if not path.is_file():
        return []
    limit = max(1, min(200, int(limit)))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines[-200:]):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
        if len(records) >= limit:
            break
    return records


def summarize_notifications(project_root: str | Path, *, limit: int = 50) -> dict[str, Any]:
    """聚合最近的队列失败通知（M31）：次数、最近时间/消息、失败图 Top 与原始记录。"""
    records = list_notifications(project_root, limit=max(1, min(200, int(limit))))
    failed_graphs: dict[str, int] = {}
    for record in records:
        for graph_id in record.get("failed_graphs") or []:
            if isinstance(graph_id, str) and graph_id:
                failed_graphs[graph_id] = failed_graphs.get(graph_id, 0) + 1
    top = sorted(failed_graphs.items(), key=lambda item: (-item[1], item[0]))[:5]
    latest = records[0] if records else None
    return {
        "count": len(records),
        "latest_at": str(latest.get("at") or "") if latest else "",
        "last_message": str(latest.get("message") or "") if latest else "",
        "failed_graphs": [{"graph_id": graph_id, "count": count} for graph_id, count in top],
        "records": records,
    }


def push_queue_alerts(
    project_root: str | Path,
    *,
    webhook_url: str,
    limit: int = 50,
    webhook_format: str = "generic",
    webhook_retries: int = 0,
) -> dict[str, Any]:
    """M32：把失败通知聚合摘要外送到 webhook（cron/告警巡检用，只读，不改队列）。"""
    url = (webhook_url or "").strip()
    if not url:
        raise FlowError("缺少 webhook 地址")
    project = _require_project(project_root)
    summary = summarize_notifications(project, limit=limit)
    failed_ids = [item["graph_id"] for item in summary["failed_graphs"]]
    message = f"队列失败告警摘要：{summary['count']} 条"
    if summary["failed_graphs"]:
        top = "、".join(f"{item['graph_id']}({item['count']})" for item in summary["failed_graphs"])
        message += f"；失败图 {top}"
    payload = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": "queue.alerts.digest",
        "project": project.name,
        "count": summary["count"],
        "latest_at": summary["latest_at"],
        "last_message": summary["last_message"],
        "failed_graphs": failed_ids,
        "message": message,
    }
    webhook = _notify_webhook(url, payload, format=webhook_format, retries=webhook_retries)
    return {"ok": bool(webhook.get("ok")), "webhook": webhook, "summary": summary, "payload": payload}


def _notify_external(notify_cmd: list[str] | None, message: str) -> bool:
    """调用外部命令外送通知（如桌面通知脚本），命令最后一个参数为通知文本。"""
    if not notify_cmd:
        return False
    try:
        subprocess.run(
            list(notify_cmd) + [message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


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
    retry_failed: int = 0,
    notify_cmd: list[str] | None = None,
    webhook_url: str | None = None,
    webhook_format: str = "generic",
    webhook_retries: int = 0,
    node_types: NodeTypeRegistry | None = None,
    sessions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 order/创建顺序执行队列中已到期的 pending 条目，返回本次结果与失败通知。

    ``retry_failed`` > 0 时，先把重试次数未用尽的失败条目重置为 pending 再执行；
    有失败时追加 JSONL 通知记录，并可用 ``notify_cmd`` 外送通知（命令末尾追加通知文本）；
    ``webhook_url`` 存在时再以 JSON POST 外送失败汇总（失败不影响队列执行）。
    """
    project = _require_project(project_root)
    doc = load_queue(project)
    limit = max(1, min(50, int(limit)))
    entries = [item for item in doc.get("entries") or [] if isinstance(item, dict)]
    now = datetime.now().astimezone()
    retry_limit = max(0, min(10, int(retry_failed or 0)))
    retried: list[str] = []
    if retry_limit:
        for entry in entries:
            if entry.get("status") == "failed" and _entry_attempts(entry) < retry_limit:
                _reset_to_pending(entry)
                retried.append(str(entry.get("queue_id")))
        if retried:
            _save(project, doc)
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
    failed_items = [item for item in ran if item.get("status") == "failed"]
    notified = False
    webhook: dict[str, Any] = {"configured": False, "ok": False}
    if failed_items:
        failed_graphs: list[str] = []
        for item in failed_items:
            for graph_id in (item.get("notification") or {}).get("failed_graphs") or []:
                graph_id = str(graph_id)
                if graph_id not in failed_graphs:
                    failed_graphs.append(graph_id)
        message = (
            f"队列运行失败 {len(failed_items)} 条（共执行 {len(ran)} 条）"
            + (f"：{', '.join(failed_graphs)}" if failed_graphs else "")
        )
        payload = {
            "at": now_iso(),
            "event": "queue.run",
            "project": project.name,
            "status": "failed",
            "message": message,
            "failed_graphs": failed_graphs,
            "ran": [
                {"queue_id": item.get("queue_id"), "status": item.get("status")}
                for item in ran
            ],
        }
        _append_notification(project, payload)
        notified = _notify_external(notify_cmd, message)
        webhook = _notify_webhook(
            webhook_url, payload, format=webhook_format, retries=webhook_retries
        )
    return {
        "ok": all(item.get("status") != "failed" for item in ran),
        "project": str(project),
        "ran": ran,
        "retried": retried,
        "notified": notified,
        "webhook": webhook,
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


def retry_entry(project_root: str | Path, queue_id: str) -> dict[str, Any]:
    """把失败条目重置为待运行（attempts+1），供手动或守护进程重试。"""
    project = _require_project(project_root)
    doc = load_queue(project)
    entry = _find_entry(doc, queue_id)
    if entry.get("status") != "failed":
        raise FlowError(f"只能重试失败条目（当前 {entry.get('status')}）：{queue_id}")
    _reset_to_pending(entry)
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
    "NOTIFY_LOG_NAME",
    "QUEUE_SCHEMA",
    "cancel_entry",
    "list_notifications",
    "list_project_roots",
    "list_queue",
    "load_queue",
    "move_entry",
    "new_queue_id",
    "normalize_schedule",
    "notify_path",
    "push_queue_alerts",
    "queue_path",
    "retry_entry",
    "run_queue",
    "summarize_notifications",
    "validate_queue",
    "write_queue",
    "enqueue",
]
