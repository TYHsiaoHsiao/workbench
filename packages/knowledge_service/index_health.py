"""索引健康巡检（M29）。

检查索引元数据/数据库/FTS 一致性与可选源目录陈旧度，输出结构化报告与处理建议。
只读，不修改索引。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .index_builder import (
    KnowledgeIndexError,
    _connect,
    _count,
    _db_path,
    _iter_source_files,
    index_ready,
)

STALE_LIST_LIMIT = 20


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _source_root_matches(meta_root: Any, requested: Path) -> bool:
    try:
        return Path(str(meta_root)).expanduser().resolve() == requested.expanduser().resolve()
    except (OSError, ValueError):
        return False


def _stale_files(conn, source_root: Path) -> dict[str, Any]:
    """比对索引记录与源目录（mtime_ns 口径）：新增/变更/删除。"""
    indexed = {
        str(row["path"]): int(row["mtime_ns"])
        for row in conn.execute("SELECT path, mtime_ns FROM documents")
    }
    present: dict[str, int] = {}
    for path in _iter_source_files(source_root):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(source_root).as_posix()
        present[rel] = stat.st_mtime_ns
    new = sorted(set(present) - set(indexed))
    removed = sorted(set(indexed) - set(present))
    changed = sorted(
        rel for rel in set(present) & set(indexed) if present[rel] != indexed[rel]
    )
    return {
        "new": new[:STALE_LIST_LIMIT],
        "changed": changed[:STALE_LIST_LIMIT],
        "removed": removed[:STALE_LIST_LIMIT],
        "new_count": len(new),
        "changed_count": len(changed),
        "removed_count": len(removed),
    }


def check_health(out_dir: str | Path, *, source_root: str | Path | None = None) -> dict[str, Any]:
    """返回索引健康报告。

    报告字段：``ok``（巡检执行成功）、``status``（healthy/problems）、``stats``、
    ``checks``（逐项 ok/detail）、``stale``（可选源目录差异）、``suggestions``。
    """
    out = Path(out_dir).expanduser()
    ready = index_ready(out)
    meta = ready["meta"]
    db_file = _db_path(out)
    checks: list[dict[str, Any]] = []
    conn = _connect(db_file)
    try:
        documents = _count(conn, "documents")
        chunks = _count(conn, "chunks")
        fts_rows = _count(conn, "chunks_fts")
        checks.append(
            _check(
                "documents",
                documents == int(meta.get("documents", -1)),
                f"数据库 {documents} / 元数据 {meta.get('documents')}",
            )
        )
        checks.append(
            _check(
                "chunks",
                chunks == int(meta.get("chunks", -1)),
                f"数据库 {chunks} / 元数据 {meta.get('chunks')}",
            )
        )
        checks.append(
            _check(
                "fts_index",
                fts_rows == chunks,
                f"FTS 行 {fts_rows} / chunks {chunks}",
            )
        )
        orphan = conn.execute(
            "SELECT COUNT(*) FROM chunks c LEFT JOIN documents d ON d.path = c.path "
            "WHERE d.path IS NULL"
        ).fetchone()[0]
        checks.append(_check("orphan_chunks", orphan == 0, f"{orphan} 个无主分块"))
        empty = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE TRIM(COALESCE(text, '')) = ''"
        ).fetchone()[0]
        checks.append(_check("empty_chunks", empty == 0, f"{empty} 个空分块"))
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM (SELECT path FROM documents GROUP BY path HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        checks.append(
            _check("duplicate_paths", duplicates == 0, f"{duplicates} 个重复文档路径")
        )
        try:
            conn.execute(
                "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", ("测试",)
            ).fetchone()
            checks.append(_check("fts_probe", True, "FTS5 MATCH 探针可用"))
        except Exception as exc:  # pragma: no cover - 依赖环境
            checks.append(_check("fts_probe", False, f"FTS5 MATCH 探针失败: {exc}"))

        stale: dict[str, Any] | None = None
        if source_root:
            root = Path(source_root).expanduser().resolve()
            if not root.is_dir():
                raise KnowledgeIndexError(f"源目录不存在或不是目录: {root}")
            checks.append(
                _check(
                    "source_root",
                    _source_root_matches(meta.get("source_root"), root),
                    f"索引源 {meta.get('source_root')} / 指定 {root}",
                )
            )
            stale = _stale_files(conn, root)
            checks.append(
                _check(
                    "stale",
                    stale["new_count"] == 0
                    and stale["changed_count"] == 0
                    and stale["removed_count"] == 0,
                    "新增 {new} / 变更 {changed} / 删除 {removed}（mtime_ns 口径）".format(
                        new=stale["new_count"],
                        changed=stale["changed_count"],
                        removed=stale["removed_count"],
                    ),
                )
            )
    finally:
        conn.close()

    suggestions: list[str] = []
    failed_names = {item["name"] for item in checks if not item["ok"]}
    if {"documents", "chunks", "fts_index", "orphan_chunks", "empty_chunks"} & failed_names:
        suggestions.append("索引结构或 FTS 不一致：重建索引 `python workbench.py index build --source <目录>`")
    if "duplicate_paths" in failed_names:
        suggestions.append("存在重复文档路径：删除索引目录后全量重建")
    if stale is not None and (stale["new_count"] or stale["changed_count"] or stale["removed_count"]):
        suggestions.append(
            "源目录有变化：执行增量维护 `python workbench.py index build --source <目录> --incremental`"
        )
    if "source_root" in failed_names:
        suggestions.append("索引来自其他源目录：确认 --source 或用当前目录重建索引")
    if not suggestions:
        suggestions.append("索引健康，无需处理")

    status = "healthy" if not failed_names else "problems"
    return {
        "ok": True,
        "status": status,
        "stats": {
            "db": str(db_file),
            "db_bytes": db_file.stat().st_size if db_file.is_file() else 0,
            "engine": (meta.get("engine") or {}).get("name"),
            "tokenizer": (meta.get("engine") or {}).get("tokenizer"),
            "documents": documents,
            "chunks": chunks,
            "fts_rows": fts_rows,
            "files_indexed": meta.get("files_indexed"),
            "files_reused": meta.get("files_reused"),
            "build_mode": meta.get("build_mode"),
        },
        "meta": {
            "index_id": meta.get("index_id"),
            "updated_at": meta.get("updated_at"),
            "source_root": meta.get("source_root"),
        },
        "checks": checks,
        "stale": stale,
        "suggestions": suggestions,
    }
