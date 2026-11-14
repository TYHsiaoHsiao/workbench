"""只读适配现有知识库索引（aistudio-md-2）。

原则：
- 只用 SQLite `mode=ro` 打开，绝不写库；
- 能力探测失败时给出明确原因，不猜测、不虚构命中；
- 外部 FTS 词条由配套 APP 私有 tokenizer 写入，是否可复用需实测后如实上报。
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

INDEX_DB_NAME = "knowledgeIndex.sqlite"
EXPECTED_SCHEMA = "aistudio-md-2"
REQUIRED_DOCUMENT_COLUMNS = {
    "id",
    "path",
    "title",
    "category",
    "kind",
    "size",
    "modified_ns",
    "sha256",
    "indexed",
}

# 各检索通道允许的分类目录（与优化 PRD 的 lane 语义一致）
LANE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "screenplay": ("05-中日韩美高热类型片", "06-全球电影节获奖剧本", "07-用户授权完整剧本"),
    "method_book": ("08-编剧方法书籍",),
    "cultural_fact": (
        "01-传统神话志怪原典",
        "02-八仙与道教传说",
        "03-历史制度民俗",
        "04-现代中国风作品研究",
    ),
    # 风格参考暂无独立语料目录；保留 lane 以兼容契约
    "style_reference": (),
}

DEFAULT_EXCLUDED_PATH_PARTS = (
    "90-",
    "10-",
    "99-",
    "待精筛",
    "正版待导入",
    "影视研究期刊",
    "新加入待分类",
)

_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")


class AdapterError(RuntimeError):
    pass


@dataclass
class ProbeResult:
    kb_root: str
    db_path: str
    exists: bool
    size_bytes: int
    schema: str | None
    documents: int
    indexed_documents: int
    categories: dict[str, int]
    kinds: dict[str, int]
    fts_external_supported: bool
    fts_note: str
    content_files: int
    issues: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_root": self.kb_root,
            "db_path": self.db_path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "schema": self.schema,
            "documents": self.documents,
            "indexed_documents": self.indexed_documents,
            "categories": self.categories,
            "kinds": self.kinds,
            "fts_external_supported": self.fts_external_supported,
            "fts_note": self.fts_note,
            "content_files": self.content_files,
            "issues": self.issues,
        }


def open_readonly(db_path: Path | str) -> sqlite3.Connection:
    """以只读 URI 打开 SQLite；文件不存在时抛 AdapterError。"""
    path = Path(db_path)
    if not path.is_file():
        raise AdapterError(f"索引文件不存在: {path}")
    uri = "file:" + quote(path.resolve().as_posix(), safe="/:") + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=10)
    except sqlite3.Error as exc:  # pragma: no cover - 防御
        raise AdapterError(f"无法只读打开索引: {path} ({exc})") from exc
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _connection(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """打开只读连接并保证关闭（Windows 下不关闭会锁住 SQLite 文件）。"""
    connection = open_readonly(db_path)
    try:
        yield connection
    finally:
        connection.close()


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }


def _count(connection: sqlite3.Connection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    return int(row[0]) if row else 0


def _try_metadata(connection: sqlite3.Connection, key: str) -> str | None:
    try:
        row = connection.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def probe(target: Path | str) -> ProbeResult:
    """探测索引指纹与可复用能力。target 可为知识库根目录或 SQLite 文件。"""
    raw = Path(target)
    db_path = raw if raw.is_file() else raw / INDEX_DB_NAME
    if not db_path.is_file():
        raise AdapterError(
            f"未找到知识库索引 {INDEX_DB_NAME}：{db_path}。"
            "请通过 --kb-root 指定知识库根目录，或设置环境变量 AI_FILM_KB_ROOT。"
        )
    issues: list[str] = []
    categories: dict[str, int] = {}
    kinds: dict[str, int] = {}
    schema: str | None = None
    documents = 0
    indexed = 0
    content_files = 0

    with _connection(db_path) as connection:
        tables = _table_names(connection)
        if "documents" not in tables:
            raise AdapterError(
                "不是可识别的 aistudio-md-2 索引：缺少 documents 表。"
                "本 PoC 只读适配该 schema；其他格式需另行迁移或重建索引。"
            )
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        missing = sorted(REQUIRED_DOCUMENT_COLUMNS - columns)
        if missing:
            issues.append("documents 缺少列: " + ", ".join(missing))
        schema = _try_metadata(connection, "schema")
        if schema is None:
            issues.append("metadata 缺少 schema 键，无法确认索引版本")
        elif schema != EXPECTED_SCHEMA:
            issues.append(f"索引 schema={schema}，与只读适配承诺的 {EXPECTED_SCHEMA} 不一致")

        documents = _count(connection, "SELECT COUNT(*) FROM documents")
        indexed = _count(connection, "SELECT COUNT(*) FROM documents WHERE indexed = 1")
        for row in connection.execute(
            "SELECT category, COUNT(*) FROM documents GROUP BY category"
        ):
            categories[str(row[0])] = int(row[1])
        for row in connection.execute("SELECT kind, COUNT(*) FROM documents GROUP BY kind"):
            kinds[str(row[0])] = int(row[1])

        kb_root = db_path.parent
        for row in connection.execute("SELECT path FROM documents WHERE indexed = 1 LIMIT 400"):
            candidate = kb_root / str(row[0])
            if candidate.is_file():
                content_files += 1
        if indexed and content_files == 0:
            issues.append("索引标记有正文的文档在磁盘上不可读（路径根不匹配或语料已移动）")

        fts_supported = False
        fts_note = "未发现 search 表，FTS 检索不可用"
        if "search" in tables:
            try:
                probe_term = "剧本"
                hits = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM search WHERE search MATCH ?", (probe_term,)
                    ).fetchone()[0]
                )
                fts_supported = hits > 0
                fts_note = (
                    f"search 表存在；MATCH('{probe_term}') 命中 {hits} 行。"
                    "词条由配套 APP 私有 tokenizer 写入，外部是否可复用以实测为准。"
                )
            except sqlite3.Error as exc:
                fts_note = f"search 表存在但外部 MATCH 不可用: {exc}"

    return ProbeResult(
        kb_root=str(db_path.parent),
        db_path=str(db_path),
        exists=True,
        size_bytes=db_path.stat().st_size,
        schema=schema,
        documents=documents,
        indexed_documents=indexed,
        categories=categories,
        kinds=kinds,
        fts_external_supported=fts_supported,
        fts_note=fts_note,
        content_files=content_files,
        issues=issues,
    )


def query_terms(text: str, max_terms: int = 24) -> list[str]:
    """从查询句中抽取 CJK 片段与英文词，作为元数据匹配与文件证据词。"""
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        value = term.strip()
        if len(value) < 2:
            return
        key = value.casefold()
        if key in seen:
            return
        seen.add(key)
        terms.append(value)

    for run in _CJK_RUN.findall(text or ""):
        add(run)
        if len(run) > 4:
            for index in range(0, len(run) - 3):
                add(run[index : index + 4])
    for word in _LATIN_WORD.findall(text or ""):
        add(word)
    return terms[:max_terms]


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_candidates(
    target: Path | str,
    terms: list[str],
    lanes: list[str],
    limit: int = 40,
    exclude_path_parts: tuple[str, ...] = DEFAULT_EXCLUDED_PATH_PARTS,
) -> tuple[list[dict[str, Any]], str]:
    """按 lane 分类白名单 + 查询词做元数据候选召回；不读取正文。"""
    allowed: set[str] = set()
    for lane in lanes:
        allowed.update(LANE_CATEGORIES.get(lane, ()))
    if not allowed:
        return [], "所选 lane 没有可用的知识库分类目录"

    sql_terms = [term for term in terms if len(term) >= 2][:10]
    if not sql_terms:
        return [], "查询词过短，无法生成候选"

    raw = Path(target)
    db_path = raw if raw.is_file() else raw / INDEX_DB_NAME
    conditions: list[str] = []
    params: list[str] = []
    for term in sql_terms:
        pattern = _like_pattern(term)
        conditions.append("(LOWER(path) LIKE ? ESCAPE '\\' OR LOWER(title) LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    sql = (
        "SELECT path, title, category, kind, indexed FROM documents WHERE ("
        + " OR ".join(conditions)
        + ")"
    )

    scored: list[dict[str, Any]] = []
    with _connection(db_path) as connection:
        for row in connection.execute(sql, params).fetchall():
            path = str(row["path"])
            title = str(row["title"] or "")
            category = str(row["category"] or "")
            if category not in allowed:
                continue
            if any(part in path for part in exclude_path_parts):
                continue
            path_l = path.casefold()
            title_l = title.casefold()
            matched = [
                term
                for term in terms
                if term.casefold() in path_l or term.casefold() in title_l
            ]
            if not matched:
                continue
            score = len(matched) * 2
            score += 1 if int(row["indexed"] or 0) == 1 else 0
            score += sum(2 for term in matched if term.casefold() in title_l)
            scored.append(
                {
                    "path": path,
                    "title": title,
                    "category": category,
                    "kind": str(row["kind"] or ""),
                    "indexed": int(row["indexed"] or 0),
                    "score": score,
                }
            )

    scored.sort(key=lambda item: (item["score"], item["indexed"], len(item["path"])), reverse=True)
    if not scored:
        return [], "元数据未命中任何候选（未读取正文，不代表知识库没有相关内容）"
    return scored[:limit], ""


def list_scan_files(
    target: Path | str,
    lanes: list[str],
    limit: int = 200,
    exclude_path_parts: tuple[str, ...] = DEFAULT_EXCLUDED_PATH_PARTS,
) -> list[dict[str, Any]]:
    """列出 lane 允许分类下、可用于有限正文回退扫描的文档行。

    与 `list_candidates` 的差异：不按查询词过滤。只做分类白名单 + 路径排除，
    由调用方按上限逐份读正文。顺序固定为 (category, path)，保证结果可复现。
    """
    allowed: set[str] = set()
    for lane in lanes:
        allowed.update(LANE_CATEGORIES.get(lane, ()))
    if not allowed or limit <= 0:
        return []

    raw = Path(target)
    db_path = raw if raw.is_file() else raw / INDEX_DB_NAME
    placeholders = ", ".join("?" for _ in allowed)
    rows: list[dict[str, Any]] = []
    with _connection(db_path) as connection:
        cursor = connection.execute(
            "SELECT path, title, category, kind, indexed FROM documents "
            f"WHERE category IN ({placeholders}) ORDER BY category, path",
            sorted(allowed),
        )
        for row in cursor:
            path = str(row["path"])
            if any(part in path for part in exclude_path_parts):
                continue
            rows.append(
                {
                    "path": path,
                    "title": str(row["title"] or ""),
                    "category": str(row["category"] or ""),
                    "kind": str(row["kind"] or ""),
                    "indexed": int(row["indexed"] or 0),
                }
            )
            if len(rows) >= limit:
                break
    return rows
