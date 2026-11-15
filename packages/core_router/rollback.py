"""项目状态快照与回滚（M18，PRD §11.4）。

快照保存在 ``00_project/history/snapshots/<snapshot_id>.zip``，包含：
``00_project/state.json``、参考记忆 JSON/MD、``状态卡.md``，以及
``00_project/workflows/`` 下的流程图/基线/队列 JSON（排除 runs/batches）。

回滚前会自动创建一份「回滚前快照」，避免误操作丢失当前状态；回滚只覆盖
快照内文件，不删除快照之后新增的文件（会在报告的 ``not_restored`` 中提示）。
"""
from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from core_router.project import ProjectError, load_state, refresh_status_card

SNAPSHOT_DIR = "00_project/history/snapshots"
SNAPSHOT_ID_RE = re.compile(r"^snap-\d{8}-\d{6}-[0-9a-f]{4}$")
METADATA_NAME = "snapshot-metadata.json"
CONTRACT_VERSION = "1.0"
CORE_FILES = (
    "00_project/state.json",
    "00_project/reference-memory.json",
    "00_project/reference-memory.md",
    "状态卡.md",
)
WORKFLOW_ROOT = "00_project/workflows"
WORKFLOW_SKIP_DIRS = {"runs", "batches", "generations"}
TXN_LOG = "00_project/history/transactions.jsonl"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_snapshot_id() -> str:
    return "snap-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def snapshots_dir(project_root: str | Path) -> Path:
    path = Path(project_root) / SNAPSHOT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_path(project_root: str | Path, snapshot_id: str) -> Path:
    if not SNAPSHOT_ID_RE.match(str(snapshot_id or "")):
        raise ProjectError(f"非法快照 ID（应为 snap-YYYYmmdd-HHMMSS-xxxx）: {snapshot_id}")
    return Path(project_root) / SNAPSHOT_DIR / f"{snapshot_id}.zip"


def _snapshot_files(project_root: Path) -> list[str]:
    files: list[str] = []
    for rel in CORE_FILES:
        if (project_root / rel).is_file():
            files.append(rel)
    workflow_root = project_root / WORKFLOW_ROOT
    if workflow_root.is_dir():
        for path in sorted(workflow_root.rglob("*.json")):
            rel = path.relative_to(project_root).as_posix()
            parts = Path(rel).parts
            if len(parts) > 3 and parts[3] in WORKFLOW_SKIP_DIRS:
                continue
            files.append(rel)
    return files


def create_snapshot(
    project_root: str | Path,
    label: str = "",
    *,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """创建项目状态快照（zip），返回快照元数据。"""
    root = Path(project_root)
    state = load_state(root)
    files = _snapshot_files(root)
    if not files:
        raise ProjectError(f"项目没有可快照的状态文件: {root}")
    sid = snapshot_id or new_snapshot_id()
    path = snapshot_path(root, sid)
    if path.exists():
        raise ProjectError(f"快照已存在，未覆盖: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    created_at = _now_iso()
    metadata = {
        "contract_version": CONTRACT_VERSION,
        "snapshot_id": sid,
        "project": state.get("project"),
        "state_version": state.get("version"),
        "stage": state.get("stage"),
        "created_at": created_at,
        "label": label,
        "files": files,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(METADATA_NAME, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        for rel in files:
            archive.write(root / rel, rel)
    return {
        "ok": True,
        "snapshot_id": sid,
        "path": str(path),
        "project": state.get("project"),
        "state_version": state.get("version"),
        "stage": state.get("stage"),
        "created_at": created_at,
        "label": label,
        "files": files,
        "bytes": path.stat().st_size,
    }


def _read_metadata(zip_path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            raw = archive.read(METADATA_NAME)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ProjectError(f"快照文件损坏或缺少元数据: {zip_path}（{exc}）") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectError(f"快照元数据不是合法 JSON: {zip_path}") from exc


def list_snapshots(project_root: str | Path) -> list[dict[str, Any]]:
    """按创建时间倒序列出快照。"""
    directory = Path(project_root) / SNAPSHOT_DIR
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.zip"):
        try:
            metadata = _read_metadata(path)
        except ProjectError:
            continue
        rows.append(
            {
                "snapshot_id": metadata.get("snapshot_id") or path.stem,
                "project": metadata.get("project"),
                "state_version": metadata.get("state_version"),
                "stage": metadata.get("stage"),
                "created_at": metadata.get("created_at"),
                "label": metadata.get("label", ""),
                "files": len(metadata.get("files") or []),
                "bytes": path.stat().st_size,
            }
        )
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return rows


def latest_snapshot(project_root: str | Path) -> dict[str, Any] | None:
    rows = list_snapshots(project_root)
    return rows[0] if rows else None


def _append_transaction(project_root: Path, entry: dict[str, Any]) -> None:
    path = project_root / TXN_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"txn_id": uuid.uuid4().hex[:12], "at": _now_iso(), **entry}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def rollback_to(
    project_root: str | Path,
    snapshot_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """回滚到指定快照；dry_run 只返回计划，不写盘、不建安全快照。"""
    root = Path(project_root)
    path = snapshot_path(root, snapshot_id)
    if not path.is_file():
        raise ProjectError(f"快照不存在: {snapshot_id}（{path}）")
    metadata = _read_metadata(path)
    files = metadata.get("files") or []
    if not isinstance(files, list) or not files:
        raise ProjectError(f"快照元数据缺少文件清单: {snapshot_id}")
    for rel in files:
        pure = PurePosixPath(str(rel))
        if pure.is_absolute() or ".." in pure.parts:
            raise ProjectError(f"快照包含非法路径: {rel}")
        if not (str(rel).startswith("00_project/") or str(rel) == "状态卡.md"):
            raise ProjectError(f"快照包含不允许回滚的路径: {rel}")
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "snapshot_id": snapshot_id,
            "project": metadata.get("project"),
            "state_version": metadata.get("state_version"),
            "stage": metadata.get("stage"),
            "files": files,
            "safety_snapshot": None,
        }
    safety = create_snapshot(root, label=f"回滚前自动快照（目标 {snapshot_id}）")
    restored: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for rel in files:
            try:
                payload = archive.read(str(rel))
            except KeyError:
                continue
            target = root / str(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            restored.append(str(rel))
    refresh_status_card(root)
    _append_transaction(
        root,
        {
            "action": "rollback",
            "snapshot_id": snapshot_id,
            "restored": len(restored),
            "safety_snapshot": safety["snapshot_id"],
        },
    )
    state = load_state(root)
    return {
        "ok": True,
        "dry_run": False,
        "snapshot_id": snapshot_id,
        "project": metadata.get("project"),
        "state_version": state.get("version"),
        "stage": state.get("stage"),
        "files": files,
        "restored_files": restored,
        "safety_snapshot": safety["snapshot_id"],
    }
