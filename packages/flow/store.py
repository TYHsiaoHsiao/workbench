"""流程文件持久化：项目内 00_project/workflows/ 与 runs/ 的读写。

约定：
- 图文件 `00_project/workflows/<graph_id>.json`（随项目迁移）；
- 运行记录 `00_project/workflows/runs/<run_id>.json`（审计用）；
- 所有写入使用"临时文件 + 原子替换"，避免半写损坏。
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from core_router.project import default_projects_root
from core_router.registry import REPO_ROOT as WORKBENCH_ROOT

from .graph import FlowError

GRAPH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUN_ID_RE = re.compile(r"^[a-z0-9-]{4,80}$")
WORKFLOWS_DIR = Path("00_project") / "workflows"
RUNS_DIR = WORKFLOWS_DIR / "runs"
GRAPH_SUFFIX = ".json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_project(ref: str | Path) -> Path:
    """把项目名或路径解析为项目根目录（必须含 00_project/state.json）。"""
    candidate = Path(ref)
    if candidate.is_dir() and (candidate / "00_project" / "state.json").is_file():
        return candidate.resolve()
    candidate = default_projects_root() / str(ref)
    if candidate.is_dir() and (candidate / "00_project" / "state.json").is_file():
        return candidate.resolve()
    raise FlowError(f"项目不存在或缺少 00_project/state.json: {ref}")


def workflows_dir(project_root: Path) -> Path:
    directory = Path(project_root) / WORKFLOWS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def runs_dir(project_root: Path) -> Path:
    directory = workflows_dir(project_root) / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def atomic_write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def graph_path(project_root: Path, graph_id: str) -> Path:
    if not GRAPH_ID_RE.match(graph_id):
        raise FlowError(f"graph_id 非法（仅小写字母、数字、连字符）: {graph_id}")
    return workflows_dir(project_root) / f"{graph_id}{GRAPH_SUFFIX}"


def read_graph_data(project_root: Path, graph_id: str) -> dict[str, Any]:
    path = graph_path(project_root, graph_id)
    if not path.is_file():
        raise FlowError(f"流程图不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"流程图读取失败: {exc}") from exc


def write_graph_data(project_root: Path, data: dict[str, Any]) -> Path:
    graph_id = str(data.get("graph_id") or "")
    if not GRAPH_ID_RE.match(graph_id):
        raise FlowError(f"graph_id 非法（仅小写字母、数字、连字符）: {graph_id}")
    data = dict(data)
    data["updated_at"] = now_iso()
    return atomic_write_json(graph_path(project_root, graph_id), data)


def list_graphs(project_root: Path) -> list[dict[str, Any]]:
    directory = workflows_dir(project_root)
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"*{GRAPH_SUFFIX}")):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "graph_id": str(data.get("graph_id") or path.stem),
                "name": str(data.get("name") or path.stem),
                "project": str(data.get("project") or ""),
                "updated_at": str(data.get("updated_at") or ""),
                "nodes": len(data.get("nodes") or []),
                "edges": len(data.get("edges") or []),
            }
        )
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items


def new_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-{secrets.token_hex(3)}"


def run_path(project_root: Path, run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id):
        raise FlowError(f"run_id 非法: {run_id}")
    return runs_dir(project_root) / f"{run_id}.json"


def write_run(project_root: Path, run: dict[str, Any]) -> Path:
    return atomic_write_json(run_path(project_root, str(run["run_id"])), run)


def read_run(project_root: Path, run_id: str) -> dict[str, Any]:
    path = run_path(project_root, run_id)
    if not path.is_file():
        raise FlowError(f"运行记录不存在: {run_id}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"运行记录读取失败: {exc}") from exc


def graph_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48]
    if not slug:
        slug = datetime.now().strftime("flow-%Y%m%d-%H%M%S")
    return slug


def list_runs(project_root: Path, limit: int = 50) -> list[dict[str, Any]]:
    """列出项目的运行记录（按开始时间倒序，读文件聚合摘要）。"""
    directory = runs_dir(project_root)
    if not directory.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        steps = data.get("steps") or []
        failed = [step for step in steps if step.get("status") == "failed"]
        runs.append(
            {
                "run_id": data.get("run_id") or path.stem,
                "graph_id": data.get("graph_id"),
                "status": data.get("status"),
                "mode": data.get("mode"),
                "dry_run": bool(data.get("dry_run")),
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "steps": len(steps),
                "failed": len(failed),
                "error": failed[0].get("error") if failed else None,
                "recovered_from": data.get("recovered_from"),
            }
        )
    runs.sort(key=lambda item: item.get("started_at") or "", reverse=True)
    return runs[: max(1, int(limit))]
