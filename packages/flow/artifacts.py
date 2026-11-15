"""产物快照与差异：对比项目创作产物在不同时间点的变化。

设计：
- 快照只记录相对路径、SHA-256、字节数与修改时间，不复制产物本体；
- 快照文件存放在 `00_project/workflows/artifacts/<snapshot_id>.json`（随项目迁移）；
- `diff_with_current` 用"最近一次快照"作为基线，与当前磁盘产物对比；
- `diff_snapshots` 对比两个快照（历史视图）。
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from .graph import FlowError
from .store import atomic_write_json, now_iso, workflows_dir

SNAPSHOT_DIR = Path("artifacts")
SNAPSHOT_PREFIX = "snap-"
TRACKED_DIRS = ("01_story", "02_script", "03_assets", "04_performance", "05_shots", "06_prompts")
MAX_FILE_BYTES = 20 * 1024 * 1024


def snapshots_dir(project_root: Path) -> Path:
    directory = workflows_dir(project_root) / SNAPSHOT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(project_root: Path) -> list[dict[str, Any]]:
    """收集受管创作目录中的文件指纹（相对路径、sha256、字节、修改时间）。"""
    root = Path(project_root)
    files: list[dict[str, Any]] = []
    for rel_dir in TRACKED_DIRS:
        base = root / rel_dir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    continue
                files.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": _sha256(path),
                        "bytes": size,
                        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                    }
                )
            except OSError:
                continue
    files.sort(key=lambda item: item["path"])
    return files


def create_snapshot(project_root: Path, label: str | None = None) -> dict[str, Any]:
    """为当前产物创建快照并写入项目，返回快照记录。"""
    files = collect_files(project_root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_id = f"{SNAPSHOT_PREFIX}{stamp}-{secrets.token_hex(3)}"
    record = {
        "contract_version": "0.1",
        "snapshot_id": snapshot_id,
        "project": Path(project_root).name,
        "label": (label or "").strip() or None,
        "created_at": now_iso(),
        "files": files,
        "summary": {
            "count": len(files),
            "bytes": sum(item["bytes"] for item in files),
        },
    }
    atomic_write_json(snapshots_dir(project_root) / f"{snapshot_id}.json", record)
    return record


def list_snapshots(project_root: Path) -> list[dict[str, Any]]:
    directory = snapshots_dir(project_root)
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{SNAPSHOT_PREFIX}*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "snapshot_id": data.get("snapshot_id") or path.stem,
                "created_at": data.get("created_at"),
                "label": data.get("label"),
                "count": (data.get("summary") or {}).get("count", 0),
                "bytes": (data.get("summary") or {}).get("bytes", 0),
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def read_snapshot(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    if not snapshot_id.startswith(SNAPSHOT_PREFIX) or "/" in snapshot_id or "\\" in snapshot_id:
        raise FlowError(f"快照 ID 非法: {snapshot_id}")
    path = snapshots_dir(project_root) / f"{snapshot_id}.json"
    if not path.is_file():
        raise FlowError(f"快照不存在: {snapshot_id}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"快照读取失败: {exc}") from exc


def latest_snapshot(project_root: Path) -> dict[str, Any] | None:
    items = list_snapshots(project_root)
    if not items:
        return None
    return read_snapshot(project_root, str(items[0]["snapshot_id"]))


def diff_files(base: list[dict[str, Any]], target: list[dict[str, Any]]) -> dict[str, Any]:
    """对比两组文件指纹：新增 / 删除 / 内容变化 / 未变。"""
    base_map = {item["path"]: item for item in base}
    target_map = {item["path"]: item for item in target}
    added = [target_map[key] for key in sorted(target_map) if key not in base_map]
    removed = [base_map[key] for key in sorted(base_map) if key not in target_map]
    changed: list[dict[str, Any]] = []
    unchanged = 0
    for key in sorted(set(base_map) & set(target_map)):
        before = base_map[key]
        after = target_map[key]
        if before.get("sha256") != after.get("sha256"):
            changed.append(
                {
                    "path": key,
                    "base_bytes": before.get("bytes"),
                    "target_bytes": after.get("bytes"),
                    "base_sha256": before.get("sha256"),
                    "target_sha256": after.get("sha256"),
                }
            )
        else:
            unchanged += 1
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": unchanged,
            "total": len(base_map) + len(added),
        },
    }


def diff_snapshots(project_root: Path, base_id: str, target_id: str) -> dict[str, Any]:
    base = read_snapshot(project_root, base_id)
    target = read_snapshot(project_root, target_id)
    result = diff_files(base.get("files") or [], target.get("files") or [])
    result.update(
        {
            "project": Path(project_root).name,
            "base_snapshot": base.get("snapshot_id"),
            "base_created_at": base.get("created_at"),
            "target_snapshot": target.get("snapshot_id"),
            "target_created_at": target.get("created_at"),
        }
    )
    return result


def diff_with_current(project_root: Path, base_id: str | None = None) -> dict[str, Any]:
    """把指定快照（默认最近一次）与当前磁盘产物对比。"""
    base = read_snapshot(project_root, base_id) if base_id else latest_snapshot(project_root)
    if base is None:
        raise FlowError("尚未创建产物快照，无法对比（先运行 project snapshot）")
    current = collect_files(project_root)
    result = diff_files(base.get("files") or [], current)
    result.update(
        {
            "project": Path(project_root).name,
            "base_snapshot": base.get("snapshot_id"),
            "base_created_at": base.get("created_at"),
            "target_snapshot": None,
            "target_created_at": None,
        }
    )
    return result


def format_diff_text(diff: dict[str, Any]) -> str:
    summary = diff.get("summary") or {}
    lines = [
        f"产物差异 · {diff.get('project')} · 基线快照 {diff.get('base_snapshot')} ({diff.get('base_created_at')})",
        f"新增 {summary.get('added', 0)} · 删除 {summary.get('removed', 0)} · 变化 {summary.get('changed', 0)} · 未变 {summary.get('unchanged', 0)}",
    ]
    for item in diff.get("added") or []:
        lines.append(f"  + {item['path']} ({item.get('bytes')}B)")
    for item in diff.get("removed") or []:
        lines.append(f"  - {item['path']} ({item.get('bytes')}B)")
    for item in diff.get("changed") or []:
        lines.append(f"  ~ {item['path']} ({item.get('base_bytes')}B → {item.get('target_bytes')}B)")
    return "\n".join(lines)
