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
import re
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
INDEX_DIR_NAME = "index"
ENGINE_NAME = "sqlite-fts5"
TOKENIZER = "trigram"
CHUNK_MAX_CHARS = 900
CHUNK_OVERLAP = 80
SOURCE_EXTENSIONS = {".md", ".markdown", ".txt"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MIN_FTS_QUERY_CHARS = 3
SEARCH_MODES = ("auto", "fts", "like", "hybrid")
HYBRID_HEADING_BONUS = 2.0
HYBRID_PATH_BONUS = 1.0
HYBRID_PHRASE_BONUS = 1.5
HYBRID_TERM_COVERAGE_BONUS = 1.0


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


def default_index_dir() -> Path:
    """索引默认目录（仓库内 ``index/``，不入发行包）。"""
    return Path(__file__).resolve().parents[2] / INDEX_DIR_NAME


def index_ready(out_dir: str | Path) -> dict[str, Any]:
    """检查索引是否可用（元数据通过契约校验且数据库存在）。

    不可用时抛 :class:`KnowledgeIndexError`，供 M22 服务层给出可读错误。
    """
    out = Path(out_dir).expanduser()
    meta = read_meta(out)
    _validate_meta(meta)
    db_file = _db_path(out)
    if not db_file.is_file():
        raise KnowledgeIndexError(
            f"索引数据库不存在: {db_file}（请先运行 index build）"
        )
    return {
        "ok": True,
        "db": str(db_file),
        "meta_path": str(_meta_path(out)),
        "meta": meta,
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


def _clean_fragment(value: Any) -> str:
    return " ".join(str(value or "").replace("[", " ").replace("]", " ").split())


def _query_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", text):
        if not token:
            continue
        if token.isascii():
            if len(token) >= 2:
                terms.append(token.lower())
            continue
        if len(token) == 1:
            terms.append(token)
        else:
            terms.extend(token[i : i + 2] for i in range(len(token) - 1))
    unique: list[str] = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique[:12] or [text]


def _rank_candidate(text: str, path: str, heading: str, snippet: str, base: float) -> float:
    """混合排序打分：基础分 + 标题/路径/短语命中 + 查询词项覆盖率。"""
    heading_text = _clean_fragment(heading)
    snippet_text = _clean_fragment(snippet)
    score = float(base)
    if text and text in heading_text:
        score += HYBRID_HEADING_BONUS
    if text and text in path:
        score += HYBRID_PATH_BONUS
    if text and text in snippet_text:
        score += HYBRID_PHRASE_BONUS
    terms = _query_terms(text)
    if terms:
        hits = sum(1 for term in terms if term in heading_text or term in snippet_text or term in path)
        score += HYBRID_TERM_COVERAGE_BONUS * (hits / len(terms))
    return round(score, 6)


def _candidate_key(path: str, heading: str, snippet: str) -> tuple[str, str]:
    # FTS 与 LIKE 的片段窗口不同（前者围绕命中词、后者从段首截断），
    # 因此按「文件 + 段落标题」去重，保留同一段落中得分最高的一条。
    return (str(path or ""), str(heading or ""))


def _fts_rows(conn: sqlite3.Connection, text: str, limit: int):
    expression = '"' + text.replace('"', '""') + '"'
    return conn.execute(
        "SELECT path, heading, snippet(chunks_fts, 2, '[', ']', '…', 12) AS snippet,"
        " bm25(chunks_fts) AS score FROM chunks_fts"
        " WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?",
        (expression, limit),
    ).fetchall()


def _like_rows(conn: sqlite3.Connection, text: str, limit: int) -> list[dict[str, Any]]:
    pattern = _like_pattern(text)
    rows = conn.execute(
        "SELECT path, heading, text FROM chunks"
        " WHERE text LIKE ? ESCAPE '\\' OR heading LIKE ? ESCAPE '\\'"
        " ORDER BY path LIMIT ?",
        (pattern, pattern, limit),
    ).fetchall()
    results: list[dict[str, Any]] = []
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
    return results


def search_index(
    out_dir: str | Path,
    query: str,
    *,
    limit: int = 8,
    mode: str = "auto",
) -> dict[str, Any]:
    """检索索引。

    ``mode``：auto（默认，>=3 字符走 FTS5 trigram、否则 LIKE 回退）、
    fts（强制 FTS，短查询报错）、like（强制 LIKE）、
    hybrid（M24：FTS + LIKE 候选合并，按标题/路径/短语/词项覆盖率加权排序）。
    """
    text = (query or "").strip()
    if not text:
        raise KnowledgeIndexError("查询词不能为空")
    if limit <= 0:
        raise KnowledgeIndexError("limit 必须为正整数")
    if mode not in SEARCH_MODES:
        raise KnowledgeIndexError(
            f"检索模式无效: {mode!r}（可选 auto/fts/like/hybrid）"
        )
    out = Path(out_dir).expanduser()
    db_file = _db_path(out)
    if not db_file.is_file():
        raise KnowledgeIndexError(f"索引数据库不存在: {db_file}（请先运行 index build）")
    conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if mode == "fts" and len(text) < MIN_FTS_QUERY_CHARS:
            raise KnowledgeIndexError("FTS 查询至少需要 3 个字符；短查询请用 like 或 hybrid 模式")
        if mode in ("auto", "fts") and len(text) >= MIN_FTS_QUERY_CHARS:
            rows = _fts_rows(conn, text, limit)
            results = [
                {
                    "path": row["path"],
                    "heading": row["heading"],
                    "snippet": row["snippet"],
                    "score": round(float(row["score"]), 6),
                }
                for row in rows
            ]
            actual = "fts"
        elif mode == "hybrid":
            candidates: list[dict[str, Any]] = []
            if len(text) >= MIN_FTS_QUERY_CHARS:
                for row in _fts_rows(conn, text, limit * 3):
                    candidates.append(
                        {
                            "path": row["path"],
                            "heading": row["heading"],
                            "snippet": row["snippet"],
                            "base": max(0.0, -float(row["score"])),
                        }
                    )
            for item in _like_rows(conn, text, limit * 2):
                candidates.append({**item, "base": 1.0})
            ranked: dict[tuple[str, str, str], dict[str, Any]] = {}
            for item in candidates:
                score = _rank_candidate(
                    text, item["path"], item["heading"], item["snippet"], item["base"]
                )
                key = _candidate_key(item["path"], item["heading"], item["snippet"])
                current = ranked.get(key)
                if current is None or score > current["score"]:
                    ranked[key] = {
                        "path": item["path"],
                        "heading": item["heading"],
                        "snippet": item["snippet"],
                        "score": score,
                    }
            results = sorted(
                ranked.values(),
                key=lambda item: (-float(item["score"]), str(item["path"]), str(item["heading"])),
            )[:limit]
            actual = "hybrid"
        else:
            results = _like_rows(conn, text, limit)
            actual = "like"
    finally:
        conn.close()
    return {
        "ok": True,
        "query": text,
        "count": len(results),
        "mode": actual,
        "results": results,
    }
