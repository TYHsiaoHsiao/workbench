"""批量运行引擎（M12）：按图逐个运行、失败自动重试并保存批次记录。

批次记录写入项目内 ``00_project/workflows/batches/<batch_id>.json``，契约校验后落盘；
每个图最多运行 ``1 + auto_retry`` 次，失败图会生成新的 run 记录（run_id 不同）。
"""
from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import validate

from . import store
from .graph import FlowError
from .registry import NodeTypeRegistry, load_node_types
from .runner import Runner

CONTRACT_VERSION = "0.1"
BATCH_SCHEMA = "flow-batch.schema.json"
BATCH_ID_RE = re.compile(r"^batch-[a-z0-9-]{4,80}$")
BATCHES_DIR_NAME = "batches"


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
    node_types: NodeTypeRegistry | None = None,
    sessions: dict[str, Runner] | None = None,
) -> dict[str, Any]:
    """批量运行流程图：逐图执行、失败自动重试，返回并保存批次记录。"""
    project = Path(project_root)
    if not (project / "00_project" / "state.json").is_file():
        raise FlowError(f"项目不存在或缺少 00_project/state.json: {project_root}")
    registry = node_types or load_node_types()
    effective_dry = True if dry_run is None else bool(dry_run)
    retry = max(0, min(3, int(auto_retry or 0)))
    limit = max(1, min(200, int(limit)))
    if all_graphs or not graph_ids:
        graph_ids = [item["graph_id"] for item in store.list_graphs(project)]
    selected: list[str] = []
    for graph_id in graph_ids or []:
        graph_id = str(graph_id or "").strip()
        if graph_id and graph_id not in selected:
            selected.append(graph_id)
    if not selected:
        raise FlowError("没有可运行的流程图")
    selected = selected[:limit]

    record: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "batch_id": new_batch_id(),
        "project": project.name,
        "dry_run": effective_dry,
        "auto_retry": retry,
        "fail_fast": bool(fail_fast),
        "status": "running",
        "started_at": now_iso(),
        "graphs": [],
        "summary": {},
    }
    batch_started = time.perf_counter()
    for graph_id in selected:
        attempts: list[dict[str, Any]] = []
        entry: dict[str, Any] = {}
        for attempt in range(1, retry + 2):
            outcome = _run_once(
                project,
                graph_id,
                dry_run=effective_dry,
                auto_confirm=auto_confirm,
                node_types=registry,
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
        record["graphs"].append(entry)
        if fail_fast and not entry["ok"]:
            break

    total_duration = int((time.perf_counter() - batch_started) * 1000)
    graphs = record["graphs"]
    succeeded = sum(1 for item in graphs if item["status"] in {"succeeded", "awaiting_confirm"})
    failed = len(graphs) - succeeded
    awaiting = sum(1 for item in graphs if item["status"] == "awaiting_confirm")
    record["status"] = "succeeded" if failed == 0 else "failed"
    record["finished_at"] = now_iso()
    record["summary"] = {
        "total": len(graphs),
        "succeeded": succeeded,
        "failed": failed,
        "awaiting_confirm": awaiting,
        "skipped": max(0, len(selected) - len(graphs)),
        "attempts": sum(len(item.get("attempts") or []) for item in graphs),
        "duration_ms": total_duration,
    }
    write_batch(project, record)
    return {"ok": record["status"] == "succeeded", "project": str(project), "batch": record}


__all__ = [
    "BATCH_SCHEMA",
    "batch_path",
    "batches_dir",
    "list_batches",
    "new_batch_id",
    "read_batch",
    "run_batch",
    "validate_batch",
    "write_batch",
]
