"""批量运行引擎（M12/M13）：按图运行、失败自动重试、可并行预演、保存批次记录并支持失败图恢复。

批次记录写入项目内 ``00_project/workflows/batches/<batch_id>.json``，契约校验后落盘；
每个图最多运行 ``1 + auto_retry`` 次，失败图会生成新的 run 记录（run_id 不同）。
``parallel=True`` 使用线程池并行执行多个图，仅支持 dry-run 预演：live 运行共享项目状态，
必须串行，避免并发写入与快照交错。
"""
from __future__ import annotations

import json
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import validate

from . import store
from .graph import FlowError
from .notify import notify_webhook
from .registry import NodeTypeRegistry, load_node_types
from .runner import Runner

CONTRACT_VERSION = "0.1"
BATCH_SCHEMA = "flow-batch.schema.json"
BATCH_ID_RE = re.compile(r"^batch-[a-z0-9-]{4,80}$")
BATCHES_DIR_NAME = "batches"
PARALLEL_WORKERS_MAX = 8


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_batch_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"batch-{stamp}-{secrets.token_hex(3)}"


def batches_dir(project_root: str | Path) -> Path:
    directory = store.workflows_dir(Path(project_root)) / BATCHES_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def batch_path(project_root: str | Path, batch_id: str) -> Path:
    if not BATCH_ID_RE.match(str(batch_id or "")):
        raise FlowError(f"非法批次 ID：{batch_id!r}")
    return batches_dir(project_root) / f"{batch_id}.json"


def validate_batch(record: dict[str, Any]) -> list[str]:
    return validate(record, schema_name=BATCH_SCHEMA)


def write_batch(project_root: str | Path, record: dict[str, Any]) -> Path:
    problems = validate_batch(record)
    if problems:
        raise FlowError("批次记录不符合契约：" + "；".join(problems))
    path = batch_path(project_root, str(record.get("batch_id") or ""))
    return store.atomic_write_json(path, record)


def read_batch(project_root: str | Path, batch_id: str) -> dict[str, Any]:
    path = batch_path(project_root, batch_id)
    if not path.is_file():
        raise FlowError(f"批次记录不存在：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlowError(f"批次记录不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise FlowError("批次记录根节点必须是对象")
    problems = validate_batch(data)
    if problems:
        raise FlowError("批次记录不符合契约：" + "；".join(problems))
    return data


def list_batches(project_root: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(200, int(limit)))
    directory = batches_dir(project_root)
    items: list[dict[str, Any]] = []
    for path in directory.glob("batch-*.json"):
        try:
            data = read_batch(project_root, path.stem)
        except FlowError:
            continue
        summary = data.get("summary") or {}
        items.append(
            {
                "batch_id": data.get("batch_id") or path.stem,
                "project": data.get("project"),
                "status": data.get("status"),
                "dry_run": bool(data.get("dry_run")),
                "auto_retry": data.get("auto_retry", 0),
                "parallel": bool(data.get("parallel")),
                "workers": data.get("workers", 1),
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "total": summary.get("total", 0),
                "succeeded": summary.get("succeeded", 0),
                "failed": summary.get("failed", 0),
                "duration_ms": summary.get("duration_ms", 0),
            }
        )
    items.sort(key=lambda item: str(item.get("started_at") or ""), reverse=True)
    return items[:limit]


def _error_from_run(run: dict[str, Any]) -> str:
    for step in run.get("steps") or []:
        if step.get("error"):
            return str(step["error"])
    return ""


def _run_once(
    project: Path,
    graph_id: str,
    *,
    dry_run: bool,
    auto_confirm: bool,
    node_types: NodeTypeRegistry | None,
    sessions: dict[str, Runner] | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        data = store.read_graph_data(project, graph_id)
        runner = Runner(
            project,
            data,
            node_types=node_types,
            dry_run=dry_run,
            auto_confirm=auto_confirm,
        )
        result = runner.run(mode="full")
        run = result["run"]
        if sessions is not None:
            sessions[str(run.get("run_id") or "")] = runner
        duration = int((time.perf_counter() - started) * 1000)
        status = str(run.get("status") or "failed")
        return {
            "attempt_status": status,
            "run_id": str(run.get("run_id") or ""),
            "steps": len(run.get("steps") or []),
            "duration_ms": duration,
            "error": _error_from_run(run),
            "runner": runner,
        }
    except (FlowError, OSError, ValueError) as exc:
        duration = int((time.perf_counter() - started) * 1000)
        return {
            "attempt_status": "error",
            "run_id": "",
            "steps": 0,
            "duration_ms": duration,
            "error": str(exc),
            "runner": None,
        }


def _run_graph(
    project: Path,
    graph_id: str,
    *,
    dry_run: bool,
    auto_confirm: bool,
    retry: int,
    node_types: NodeTypeRegistry | None,
    sessions: dict[str, Runner] | None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    entry: dict[str, Any] = {}
    for attempt in range(1, retry + 2):
        outcome = _run_once(
            project,
            graph_id,
            dry_run=dry_run,
            auto_confirm=auto_confirm,
            node_types=node_types,
            sessions=sessions,
        )
        attempts.append(
            {
                "attempt": attempt,
                "run_id": outcome["run_id"],
                "status": outcome["attempt_status"],
                "duration_ms": outcome["duration_ms"],
                "error": outcome["error"],
            }
        )
        entry = {
            "graph_id": graph_id,
            "ok": outcome["attempt_status"] in {"succeeded", "awaiting_confirm"},
            "status": outcome["attempt_status"],
            "run_id": outcome["run_id"],
            "steps": outcome["steps"],
            "duration_ms": outcome["duration_ms"],
            "error": outcome["error"],
            "attempts": attempts,
        }
        if entry["ok"]:
            break
    return entry


def _require_project(project_root: str | Path) -> Path:
    project = Path(project_root)
    if not (project / "00_project" / "state.json").is_file():
        raise FlowError(f"项目不存在或缺少 00_project/state.json: {project_root}")
    return project


def _select_graphs(
    project: Path,
    graph_ids: list[str] | None,
    *,
    all_graphs: bool,
    limit: int,
) -> list[str]:
    if all_graphs or not graph_ids:
        graph_ids = [item["graph_id"] for item in store.list_graphs(project)]
    selected: list[str] = []
    for graph_id in graph_ids or []:
        graph_id = str(graph_id or "").strip()
        if graph_id and graph_id not in selected:
            selected.append(graph_id)
    if not selected:
        raise FlowError("没有可运行的流程图")
    return selected[:limit]


def _normalize_workers(workers: int | None) -> int:
    return max(1, min(PARALLEL_WORKERS_MAX, int(workers or 2)))


def _check_parallel(parallel: bool, dry_run: bool, fail_fast: bool) -> None:
    if not parallel:
        return
    if not dry_run:
        raise FlowError("并行批次仅支持 dry-run 预演；live 运行会共享项目状态，请串行执行")
    if fail_fast:
        raise FlowError("并行批次不支持 fail_fast（请改用串行批次）")


def _execute(
    project: Path,
    selected: list[str],
    *,
    dry_run: bool,
    auto_confirm: bool,
    retry: int,
    fail_fast: bool,
    node_types: NodeTypeRegistry | None,
    sessions: dict[str, Runner] | None,
    parallel: bool,
    workers: int,
) -> list[dict[str, Any]]:
    if parallel:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _run_graph,
                    project,
                    graph_id,
                    dry_run=dry_run,
                    auto_confirm=auto_confirm,
                    retry=retry,
                    node_types=node_types,
                    sessions=sessions,
                )
                for graph_id in selected
            ]
            return [future.result() for future in futures]
    entries: list[dict[str, Any]] = []
    for graph_id in selected:
        entry = _run_graph(
            project,
            graph_id,
            dry_run=dry_run,
            auto_confirm=auto_confirm,
            retry=retry,
            node_types=node_types,
            sessions=sessions,
        )
        entries.append(entry)
        if fail_fast and not entry["ok"]:
            break
    return entries


def _summarize(
    graphs: list[dict[str, Any]],
    *,
    selected_total: int,
    duration_ms: int,
) -> dict[str, Any]:
    succeeded = sum(1 for item in graphs if item["status"] in {"succeeded", "awaiting_confirm"})
    failed = len(graphs) - succeeded
    awaiting = sum(1 for item in graphs if item["status"] == "awaiting_confirm")
    return {
        "total": len(graphs),
        "succeeded": succeeded,
        "failed": failed,
        "awaiting_confirm": awaiting,
        "skipped": max(0, selected_total - len(graphs)),
        "attempts": sum(len(item.get("attempts") or []) for item in graphs),
        "duration_ms": duration_ms,
    }


def run_batch(
    project_root: str | Path,
    graph_ids: list[str] | None = None,
    *,
    all_graphs: bool = False,
    dry_run: bool | None = None,
    auto_confirm: bool = True,
    auto_retry: int = 0,
    fail_fast: bool = False,
    limit: int = 20,
    parallel: bool = False,
    workers: int = 2,
    node_types: NodeTypeRegistry | None = None,
    sessions: dict[str, Runner] | None = None,
    webhook_url: str | None = None,
    webhook_format: str = "generic",
    webhook_retries: int = 0,
) -> dict[str, Any]:
    """批量运行流程图：按图执行（可并行预演）、失败自动重试，返回并保存批次记录。

    ``webhook_url`` 存在且批次有失败图时，把失败汇总以 JSON POST 外送
    （M28；失败不影响批次执行），返回值 ``webhook`` 记录外送结果。
    """
    project = _require_project(project_root)
    registry = node_types or load_node_types()
    effective_dry = True if dry_run is None else bool(dry_run)
    retry = max(0, min(3, int(auto_retry or 0)))
    limit = max(1, min(200, int(limit)))
    worker_count = _normalize_workers(workers)
    _check_parallel(bool(parallel), effective_dry, bool(fail_fast))
    selected = _select_graphs(project, graph_ids, all_graphs=all_graphs, limit=limit)

    record: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "batch_id": new_batch_id(),
        "project": project.name,
        "dry_run": effective_dry,
        "auto_retry": retry,
        "fail_fast": bool(fail_fast),
        "parallel": bool(parallel),
        "workers": worker_count,
        "status": "running",
        "started_at": now_iso(),
        "graphs": [],
        "summary": {},
    }
    batch_started = time.perf_counter()
    record["graphs"] = _execute(
        project,
        selected,
        dry_run=effective_dry,
        auto_confirm=auto_confirm,
        retry=retry,
        fail_fast=bool(fail_fast),
        node_types=registry,
        sessions=sessions,
        parallel=bool(parallel),
        workers=worker_count,
    )
    total_duration = int((time.perf_counter() - batch_started) * 1000)
    summary = _summarize(record["graphs"], selected_total=len(selected), duration_ms=total_duration)
    record["summary"] = summary
    record["status"] = "succeeded" if summary["failed"] == 0 else "failed"
    record["finished_at"] = now_iso()
    write_batch(project, record)
    webhook = {"configured": bool(webhook_url), "ok": False}
    if summary["failed"] and webhook_url:
        failed_graphs = [item["graph_id"] for item in record["graphs"] if not item.get("ok")]
        payload = {
            "at": now_iso(),
            "event": "batch.run",
            "project": project.name,
            "batch_id": record["batch_id"],
            "status": record["status"],
            "message": f"批次 {record['batch_id']} 失败 {len(failed_graphs)} 个图：{', '.join(failed_graphs)}",
            "failed_graphs": failed_graphs,
            "summary": summary,
        }
        webhook = notify_webhook(
            webhook_url, payload, format=webhook_format, retries=webhook_retries
        )
    return {
        "ok": record["status"] == "succeeded",
        "project": str(project),
        "batch": record,
        "webhook": webhook,
    }


def recover_batch(
    project_root: str | Path,
    batch_id: str,
    *,
    dry_run: bool | None = None,
    auto_confirm: bool = True,
    auto_retry: int = 0,
    parallel: bool = False,
    workers: int = 2,
    node_types: NodeTypeRegistry | None = None,
    sessions: dict[str, Runner] | None = None,
) -> dict[str, Any]:
    """重跑批次中的失败图，把新的尝试追加到原批次记录并更新汇总。"""
    project = _require_project(project_root)
    record = read_batch(project, batch_id)
    failed_graphs = [str(item.get("graph_id")) for item in record.get("graphs") or [] if not item.get("ok")]
    if not failed_graphs:
        return {"ok": True, "project": str(project), "batch": record, "recovered": 0}

    registry = node_types or load_node_types()
    effective_dry = bool(record.get("dry_run", True)) if dry_run is None else bool(dry_run)
    retry = max(0, min(3, int(auto_retry or 0)))
    worker_count = _normalize_workers(workers)
    _check_parallel(bool(parallel), effective_dry, False)

    recovered_entries = _execute(
        project,
        failed_graphs,
        dry_run=effective_dry,
        auto_confirm=auto_confirm,
        retry=retry,
        fail_fast=False,
        node_types=registry,
        sessions=sessions,
        parallel=bool(parallel),
        workers=worker_count,
    )
    recovered_by_id = {entry["graph_id"]: entry for entry in recovered_entries}
    for original in record.get("graphs") or []:
        new_entry = recovered_by_id.get(str(original.get("graph_id")))
        if new_entry is None:
            continue
        base_attempt = len(original.get("attempts") or [])
        merged_attempts = list(original.get("attempts") or [])
        for offset, attempt in enumerate(new_entry.get("attempts") or []):
            merged_attempts.append({**attempt, "attempt": base_attempt + offset + 1})
        for key in ("ok", "status", "run_id", "steps", "duration_ms", "error"):
            original[key] = new_entry.get(key)
        original["attempts"] = merged_attempts

    graphs = record.get("graphs") or []
    succeeded = sum(1 for item in graphs if item.get("status") in {"succeeded", "awaiting_confirm"})
    failed = len(graphs) - succeeded
    awaiting = sum(1 for item in graphs if item.get("status") == "awaiting_confirm")
    record["status"] = "succeeded" if failed == 0 else "failed"
    record["finished_at"] = now_iso()
    record["summary"] = {
        "total": len(graphs),
        "succeeded": succeeded,
        "failed": failed,
        "awaiting_confirm": awaiting,
        "skipped": int((record.get("summary") or {}).get("skipped", 0)),
        "attempts": sum(len(item.get("attempts") or []) for item in graphs),
        "duration_ms": sum(int(item.get("duration_ms") or 0) for item in graphs),
    }
    write_batch(project, record)
    return {
        "ok": record["status"] == "succeeded",
        "project": str(project),
        "batch": record,
        "recovered": len(recovered_entries),
    }


__all__ = [
    "BATCH_SCHEMA",
    "PARALLEL_WORKERS_MAX",
    "batch_path",
    "batches_dir",
    "list_batches",
    "new_batch_id",
    "read_batch",
    "recover_batch",
    "run_batch",
    "validate_batch",
    "write_batch",
]
