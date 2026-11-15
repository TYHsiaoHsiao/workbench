"""项目状态写锁与事务日志（M6）。

并行波内可能同时存在多个写状态节点。为保证 ``state.json`` 的
read-modify-write 不被交错覆盖，写状态节点在持锁期间执行，并把每次
写操作追加到 ``00_project/history/transactions.jsonl``，便于审计与
人工复核（不提供自动回滚）。

锁为项目级文件锁：``00_project/.locks/state.lock``。
进程崩溃遗留的锁在超过 ``STALE_SECONDS`` 后会被自动清理。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

LOCK_DIR = "00_project/.locks"
LOCK_NAME = "state.lock"
TXN_LOG = "00_project/history/transactions.jsonl"
STALE_SECONDS = 120.0


class LockError(RuntimeError):
    """等待状态锁超时。"""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def state_lock(project_root: Path | str, timeout: float = 15.0) -> Iterator[dict[str, Any]]:
    """获取项目状态写锁；超时抛 LockError。"""
    root = Path(project_root)
    lock_dir = root / LOCK_DIR
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / LOCK_NAME

    deadline = time.monotonic() + max(0.1, timeout)
    fd: int | None = None
    info: dict[str, Any] = {"path": str(lock_path), "waited_s": 0.0}
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "at": _now_iso()}, ensure_ascii=False).encode("utf-8"))
            info["waited_s"] = round(max(0.0, timeout - (deadline - time.monotonic())), 3)
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise LockError(f"等待项目状态锁超时（{timeout:.1f}s）: {lock_path}")
            time.sleep(0.05)

    try:
        yield info
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:  # pragma: no cover
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass


def log_transaction(project_root: Path | str, entry: dict[str, Any]) -> Path:
    """追加一条事务日志（JSON Lines）。"""
    root = Path(project_root)
    path = root / TXN_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"txn_id": uuid.uuid4().hex[:12], "at": _now_iso(), **entry}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
