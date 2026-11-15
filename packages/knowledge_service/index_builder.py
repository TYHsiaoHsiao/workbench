"""知识库索引维护（FR-10 / M21）：按契约重建与增量维护本地 SQLite FTS5 索引。

设计要点（PRD D1 方案 B 的基础版，零第三方依赖）：

- 只读扫描来源目录（.md/.markdown/.txt），按标题/段落分块后写入 SQLite；
- 检索使用 FTS5 ``trigram`` tokenizer（>= SQLite 3.34），对中文无需分词即可子串匹配，
  短于 3 个字符的查询自动回退为 LIKE；
- 全量构建与增量维护共用同一份元数据（``knowledge-index-meta.json``），并受
  ``knowledge-index.schema.json`` 契约约束；
- 索引文件不写入项目目录，默认落在 ``workbench/index/``（可被 .gitignore 忽略）。
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts import validate

INDEX_SCHEMA = "knowledge-index.schema.json"
INDEX_SCHEMA_VERSION = "1"
INDEX_DB_NAME = "knowledge-index.sqlite"
INDEX_META_NAME = "knowledge-index-meta.json"
ENGINE_NAME = "sqlite-fts5"
TOKENIZER = "trigram"
CHUNK_MAX_CHARS = 900
CHUNK_OVERLAP = 80
SOURCE_EXTENSIONS = {".md", ".markdown", ".txt"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MIN_FTS_QUERY_CHARS = 3


class KnowledgeIndexError(RuntimeError):
    """索引构建/维护/检索失败。"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_source_files(source_root: Path):
    """按稳定顺序遍历可索引的正文文件。"""
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        parts = set(path.relative_to(source_root).parts[:-1])
        if parts & SKIP_DIRS:
            continue
        if any(part.startswith(".") for part in path.relative_to(source_root).parts):
            continue
        yield path


def split_chunks(text: str) -> list[tuple[str, str]]:
    """把正文切成 ``(标题路径, 分块文本)`` 列表（确定性、无随机性）。"""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[tuple[str, str]] = []
    heading = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        body = "\n".join(buffer).strip()
        if body:
            blocks.append((heading, body))
        buffer = []

    for line in normalized.split("\n"):
        if line.lstrip().startswith("#"):
            flush()
            title = line.strip().lstrip("#").strip()
            if title:
                heading = title
        elif not line.strip():
            flush()
        else:
            buffer.append(line.rstrip())
    flush()

    merged: list[tuple[str, str]] = []
    current_heading = ""
    current: list[str] = []
    for head, body in blocks:
        candidate = "\n\n".join(current + [body])
        if current and (head != current_heading or len(candidate) > CHUNK_MAX_CHARS):
            merged.append((current_heading, "\n\n".join(current)))
            current = []
        if not current:
            current_heading = head
        current.append(body)
    if current:
        merged.append((current_heading, "\n\n".join(current)))

    chunks: list[tuple[str, str]] = []
    for head, body in merged:
        while len(body) > CHUNK_MAX_CHARS:
            chunks.append((head, body[:CHUNK_MAX_CHARS]))
            body = body[max(0, CHUNK_MAX_CHARS - CHUNK_OVERLAP):]
        if body.strip():
            chunks.append((head, body.strip()))
    return chunks


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "path, heading, text, tokenize='trigram')"
        )
    except sqlite3.OperationalError as exc:  # pragma: no cover - 旧 SQLite 兜底
        raise KnowledgeIndexError(
            f"当前 SQLite 不支持 FTS5 trigram tokenizer（需要 SQLite >= 3.34）：{exc}"
        ) from exc
    conn.execute(
        "CREATE TABLE IF NOT EXISTS documents ("
        "path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,"
        " mtime_ns INTEGER NOT NULL, chunks INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chunks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL,"
        " heading TEXT NOT NULL, text TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
    conn.commit()


def _delete_document(conn: sqlite3.Connection, rel_path: str) -> None:
    rows = conn.execute("SELECT id FROM chunks WHERE path = ?", (rel_path,)).fetchall()
    conn.executemany("DELETE FROM chunks_fts WHERE rowid = ?", [(row["id"],) for row in rows])
    conn.execute("DELETE FROM chunks WHERE path = ?", (rel_path,))
    conn.execute("DELETE FROM documents WHERE path = ?", (rel_path,))


def _index_document(conn: sqlite3.Connection, source_root: Path, path: Path) -> int:
    rel_path = path.relative_to(source_root).as_posix()
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    chunks = split_chunks(text)
    _delete_document(conn, rel_path)
    stat = path.stat()
    conn.execute(
        "INSERT INTO documents(path, sha256, bytes, mtime_ns, chunks) VALUES(?,?,?,?,?)",
        (rel_path, hashlib.sha256(raw).hexdigest(), len(raw), stat.st_mtime_ns, len(chunks)),
    )
    for heading, body in chunks:
        cursor = conn.execute(
            "INSERT INTO chunks(path, heading, text) VALUES(?,?,?)",
            (rel_path, heading, body),
        )
        conn.execute(
            "INSERT INTO chunks_fts(rowid, path, heading, text) VALUES(?,?,?,?)",
            (cursor.lastrowid, rel_path, heading, body),
        )
    return len(chunks)


def _new_index_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"idx-{stamp}-{secrets.token_hex(3)}"


def _meta_path(out_dir: Path) -> Path:
    return out_dir / INDEX_META_NAME


def _db_path(out_dir: Path) -> Path:
    return out_dir / INDEX_DB_NAME


def read_meta(out_dir: str | Path) -> dict[str, Any]:
    meta_file = _meta_path(Path(out_dir))
    if not meta_file.is_file():
        raise KnowledgeIndexError(
            f"索引元数据不存在: {meta_file}（请先运行 index build）"
        )
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeIndexError(f"索引元数据无法读取: {exc}") from exc
    return meta


def _validate_meta(meta: dict[str, Any]) -> None:
    errors = validate(meta, schema_name=INDEX_SCHEMA)
    if errors:
        raise KnowledgeIndexError("索引元数据契约校验失败：" + "; ".join(errors))


def _write_meta(out_dir: Path, meta: dict[str, Any]) -> Path:
    _validate_meta(meta)
    meta_file = _meta_path(out_dir)
    meta_file.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta_file


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def build_index(
    source_root: str | Path,
    out_dir: str | Path,
    *,
    incremental: bool = False,
    index_id: str | None = None,
) -> dict[str, Any]:
    """构建（或增量维护）索引；返回构建摘要。"""
    source = Path(source_root).expanduser()
    if not source.is_dir():
        raise KnowledgeIndexError(f"来源目录不存在: {source}")
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    db_file = _db_path(out)

    existing_meta: dict[str, Any] | None = None
    documents: dict[str, tuple[str, int]] = {}
    if incremental and db_file.is_file() and _meta_path(out).is_file():
        try:
            existing_meta = read_meta(out)
            _validate_meta(existing_meta)
        except KnowledgeIndexError:
            existing_meta = None
        if existing_meta is not None:
            conn = _connect(db_file)
            try:
                rows = conn.execute("SELECT path, sha256, mtime_ns FROM documents").fetchall()
                documents = {row["path"]: (row["sha256"], int(row["mtime_ns"])) for row in rows}
            finally:
                conn.close()

    full_build = existing_meta is None
    if full_build:
        if db_file.is_file():
            db_file.unlink()
        documents = {}

    conn = _connect(db_file)
    try:
        _create_schema(conn)
        files = list(_iter_source_files(source))
        seen: set[str] = set()
        indexed = reused = removed = 0
        bytes_source = 0
        for path in files:
            rel_path = path.relative_to(source).as_posix()
            seen.add(rel_path)
            stat = path.stat()
            bytes_source += stat.st_size
            old = documents.get(rel_path)
            if old is not None and old[1] == stat.st_mtime_ns:
                reused += 1
                continue
            _index_document(conn, source, path)
            indexed += 1
        for rel_path in sorted(set(documents) - seen):
            _delete_document(conn, rel_path)
            removed += 1
        conn.commit()
        documents_count = _count(conn, "documents")
        chunks_count = _count(conn, "chunks")
    finally:
        conn.close()

    created_at = (
        existing_meta["created_at"] if existing_meta is not None else now_iso()
    )
    meta = {
        "contract_version": "0.1",
        "index_id": index_id or (existing_meta["index_id"] if existing_meta else _new_index_id()),
        "build_mode": "incremental" if (incremental and existing_meta is not None) else "full",
        "source_root": str(source.resolve()),
        "engine": {
            "name": ENGINE_NAME,
            "tokenizer": TOKENIZER,
            "schema_version": INDEX_SCHEMA_VERSION,
        },
        "created_at": created_at,
        "updated_at": now_iso(),
        "documents": documents_count,
        "chunks": chunks_count,
        "files_total": len(files),
        "files_indexed": indexed,
        "files_reused": reused,
        "files_removed": removed,
        "bytes_source": bytes_source,
    }
    meta_file = _write_meta(out, meta)
    return {
        "ok": True,
        "db": str(db_file),
        "meta": str(meta_file),
        "meta_data": meta,
    }


def index_info(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir).expanduser()
    meta = read_meta(out)
    db_file = _db_path(out)
    if not db_file.is_file():
        raise KnowledgeIndexError(f"索引数据库不存在: {db_file}")
    return {
        "ok": True,
        "db": str(db_file),
        "db_bytes": db_file.stat().st_size,
        "meta": str(_meta_path(out)),
        "meta_data": meta,
    }


def verify_index(out_dir: str | Path) -> dict[str, Any]:
    """校验索引库与元数据是否一致、FTS 是否可查询。"""
    out = Path(out_dir).expanduser()
    errors: list[str] = []
    meta: dict[str, Any] | None = None
    db_file = _db_path(out)
    try:
        meta = read_meta(out)
        _validate_meta(meta)
    except KnowledgeIndexError as exc:
        errors.append(str(exc))
    if not db_file.is_file():
        errors.append(f"索引数据库不存在: {db_file}")
    if meta is not None and db_file.is_file():
        try:
            conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
            try:
                documents = _count(conn, "documents")
                chunks = _count(conn, "chunks")
                fts = _count(conn, "chunks_fts")
                if documents != meta["documents"]:
                    errors.append(
                        f"文档数不一致：元数据 {meta['documents']}，数据库 {documents}"
                    )
                if chunks != meta["chunks"]:
                    errors.append(f"分块数不一致：元数据 {meta['chunks']}，数据库 {chunks}")
                if fts != chunks:
                    errors.append(f"FTS 行数不一致：分块 {chunks}，FTS {fts}")
                try:
                    conn.execute("SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", ("测试",))
                except sqlite3.Error as exc:
                    errors.append(f"FTS 查询失败: {exc}")
            finally:
                conn.close()
        except sqlite3.Error as exc:
            errors.append(f"索引数据库无法读取: {exc}")
    return {
        "ok": not errors,
        "errors": errors,
        "db": str(db_file),
        "meta": str(_meta_path(out)),
        "meta_data": meta,
    }


def _like_pattern(query: str) -> str:
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_index(
    out_dir: str | Path,
    query: str,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """检索索引：>=3 字符走 FTS5 trigram，否则 LIKE 回退。"""
    text = (query or "").strip()
    if not text:
        raise KnowledgeIndexError("查询词不能为空")
    if limit <= 0:
        raise KnowledgeIndexError("limit 必须为正整数")
    out = Path(out_dir).expanduser()
    db_file = _db_path(out)
    if not db_file.is_file():
        raise KnowledgeIndexError(f"索引数据库不存在: {db_file}（请先运行 index build）")
    results: list[dict[str, Any]] = []
    conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if len(text) >= MIN_FTS_QUERY_CHARS:
            expression = '"' + text.replace('"', '""') + '"'
            rows = conn.execute(
                "SELECT path, heading, snippet(chunks_fts, 2, '[', ']', '…', 12) AS snippet,"
                " bm25(chunks_fts) AS score FROM chunks_fts"
                " WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?",
                (expression, limit),
            ).fetchall()
            for row in rows:
                results.append(
                    {
                        "path": row["path"],
                        "heading": row["heading"],
                        "snippet": row["snippet"],
                        "score": round(float(row["score"]), 6),
                    }
                )
        else:
            pattern = _like_pattern(text)
            rows = conn.execute(
                "SELECT path, heading, text FROM chunks"
                " WHERE text LIKE ? ESCAPE '\\' OR heading LIKE ? ESCAPE '\\'"
                " ORDER BY path LIMIT ?",
                (pattern, pattern, limit),
            ).fetchall()
            for row in rows:
                body = str(row["text"]).replace("\n", " ")
                results.append(
                    {
                        "path": row["path"],
                        "heading": row["heading"],
                        "snippet": body[:160],
                        "score": None,
                    }
                )
    finally:
        conn.close()
    return {
        "ok": True,
        "query": text,
        "count": len(results),
        "mode": "fts" if len(text) >= MIN_FTS_QUERY_CHARS else "like",
        "results": results,
    }
