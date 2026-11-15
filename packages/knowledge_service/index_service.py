"""知识服务：把按契约重建的索引接入证据卡流程（M22 / FR-10 增强）。

与 :mod:`service` 的外部知识库路径互补：

- 检索只读 ``index/``（M21 产物），不触碰外部知识库；
- 证据仍保持四字段（路径 / 页码或段落 / 片段 / 命中词），可直接进入确认流程；
- 生成同样受 ``knowledge-card.schema.json`` 约束的知识卡，供 flow 节点与 CLI 复用。
"""
from __future__ import annotations

from typing import Any

from contracts import validate

from .index_builder import (
    KnowledgeIndexError,
    default_index_dir,
    index_ready,
    search_index,
)
from .service import SCOPE_BY_STAGE

CARD_SCHEMA = "knowledge-card.schema.json"
MAX_QUERY_LEN = 200
LANE_ENUM = ("screenplay", "method_book", "cultural_fact", "style_reference")


class KnowledgeIndexServiceError(ValueError):
    """索引证据卡参数/检索失败。"""


def _normalize_queries(queries: Any) -> list[dict[str, str]]:
    if not isinstance(queries, (list, tuple)) or not queries:
        raise KnowledgeIndexServiceError("queries 至少需要 1 条查询")
    normalized: list[dict[str, str]] = []
    for item in queries:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                raise KnowledgeIndexServiceError("查询词不能为空")
            if ":" in text:
                lane, query = text.split(":", 1)
                lane = lane.strip() or "screenplay"
                query = query.strip()
            else:
                lane, query = "screenplay", text
        elif isinstance(item, dict):
            lane = str(item.get("lane") or "screenplay").strip() or "screenplay"
            query = str(item.get("query") or "").strip()
        else:
            raise KnowledgeIndexServiceError("queries 项必须是字符串或 {lane, query} 对象")
        if not query:
            raise KnowledgeIndexServiceError("查询词不能为空")
        if len(query) > MAX_QUERY_LEN:
            raise KnowledgeIndexServiceError(
                f"查询词过长（>{MAX_QUERY_LEN} 字符）: {query[:20]}…"
            )
        if lane not in LANE_ENUM:
            lane = "screenplay"
        normalized.append({"lane": lane, "query": query})
    return normalized


def search_index_card(
    project: str,
    stage: str,
    problem: str,
    queries: Any,
    *,
    index_dir: str | None = None,
    evidence_limit: int = 8,
    per_query_limit: int = 8,
) -> dict[str, Any]:
    """用本地索引生成 evidence 链知识卡。

    返回 ``{"ok", "status", "card", "report"}``，结构对齐 :func:`service.search`。
    """
    project = str(project or "").strip()
    problem = str(problem or "").strip()
    stage = str(stage or "").strip()
    if not project:
        raise KnowledgeIndexServiceError("project 不能为空")
    if not problem:
        raise KnowledgeIndexServiceError("problem 不能为空")
    if stage not in SCOPE_BY_STAGE:
        raise KnowledgeIndexServiceError(f"stage 无效: {stage!r}（应为 01–08）")
    if not isinstance(evidence_limit, int) or evidence_limit < 1:
        raise KnowledgeIndexServiceError("evidence_limit 必须为正整数")
    if not isinstance(per_query_limit, int) or per_query_limit < 1:
        raise KnowledgeIndexServiceError("per_query_limit 必须为正整数")

    raw_queries = _normalize_queries(queries)
    out_dir = default_index_dir() if not index_dir else index_dir
    try:
        ready = index_ready(out_dir)
    except KnowledgeIndexError as exc:
        raise KnowledgeIndexServiceError(str(exc)) from exc
    meta = ready["meta"]

    collected: list[dict[str, Any]] = []
    query_modes: dict[str, str] = {}
    for item in raw_queries:
        query = item["query"]
        result = search_index(out_dir, query, limit=per_query_limit, mode="hybrid")
        query_modes[query] = result["mode"]
        for hit in result["results"]:
            heading = (hit.get("heading") or "").strip()
            collected.append(
                {
                    "path": hit["path"],
                    "page": heading or "行 1",
                    "snippet": (hit.get("snippet") or "").strip(),
                    "hit": query,
                    "score": hit.get("score"),
                    "mode": result["mode"],
                }
            )

    # 去重（同文件同段落同片段只保留一条，命中词取首次出现的查询；snippet 的
    # 高亮方括号不参与比较），FTS 按 bm25 升序优先，LIKE 靠后。
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in collected:
        snippet_key = entry["snippet"].replace("[", "").replace("]", "")
        key = (entry["path"], entry["page"], snippet_key)
        if key not in deduped:
            deduped[key] = entry
    def _rank_key(entry: dict[str, Any]) -> tuple[int, float, str, str]:
        score = entry.get("score")
        if score is None:
            return (1, 0.0, entry["path"], entry["page"])
        value = float(score)
        if entry.get("mode") == "hybrid":
            return (0, -value, entry["path"], entry["page"])
        return (0, value, entry["path"], entry["page"])

    ordered = sorted(deduped.values(), key=_rank_key)
    evidence = [
        {
            "path": entry["path"],
            "page": entry["page"],
            "snippet": entry["snippet"],
            "hit": entry["hit"],
        }
        for entry in ordered[:evidence_limit]
    ]

    candidates: list[str] = []
    for entry in ordered:
        if entry["path"] not in candidates:
            candidates.append(entry["path"])

    scope = [SCOPE_BY_STAGE[stage]]
    card = {
        "contract_version": "1.0",
        "card_id": f"{project}-{stage}-{meta['index_id']}",
        "project": project,
        "stage": stage,
        "query_profile": {
            "problem": problem,
            "queries": [{"lane": q["lane"], "query": q["query"]} for q in raw_queries],
        },
        "evidence": evidence,
        "candidates": candidates,
        "selected_documents": [],
        "deep_read_selected": False,
        "confirmed": {"by": "", "at": ""},
        "scope": scope,
    }
    errors = validate(card, schema_name=CARD_SCHEMA)
    if errors:
        raise KnowledgeIndexServiceError(
            "索引知识卡契约校验失败：" + "；".join(errors[:3])
        )

    status = "ok" if evidence else "no_evidence"
    statement = (
        "已从按契约重建的本地索引形成文件级证据（路径/段落/片段/命中词齐全），"
        "可进入确认流程；未写入参考记忆。"
        if evidence
        else "本地索引未命中可用证据，请调整查询词或重建索引；未写入参考记忆。"
    )
    report: dict[str, Any] = {
        "status": status,
        "statement": statement,
        "source": "index",
        "index_root": str(out_dir),
        "index_id": meta["index_id"],
        "build_mode": meta["build_mode"],
        "documents": meta["documents"],
        "chunks": meta["chunks"],
        "source_root": meta["source_root"],
        "queries": raw_queries,
        "query_modes": query_modes,
        "candidates": len(candidates),
        "evidence": len(evidence),
        "read_only": True,
    }
    return {"ok": status == "ok", "status": status, "card": card, "report": report}
