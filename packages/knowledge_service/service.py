"""知识服务 PoC：只读适配现有索引 + 元数据候选 + 文件级证据 + knowledge-card 契约输出。

边界：
- 不修改知识库本体（SQLite 只读、文件只读）；
- 没有「路径 + 行号/页码 + 片段 + 命中词」四要素时，不生成证据，且明确报告未形成可证明命中；
- 候选召回不等于命中：候选未读正文前只进入 `candidates`，不进入 `evidence`。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from contracts import validate
from core_router.registry import REPO_ROOT

from .adapter import (
    AdapterError,
    INDEX_DB_NAME,
    LANE_CATEGORIES,
    list_candidates,
    list_scan_files,
    probe,
    query_terms,
)
from .evidence import EVIDENCE_EXTENSIONS, scan_file_scored

WORKBENCH_CONFIG = Path.home() / ".ai-film-workbench" / "config.json"

# 有限正文回退扫描的默认预算（只读；用于补足元数据召回不足）
FALLBACK_MAX_FILES = 200
FALLBACK_MAX_FILE_BYTES = 256 * 1024

# 证据置信度策略：达到该分数的证据视为「有结构语境/叙事搭配/多词共现」支撑。
# 当高置信证据不少于 MIN_HIGH_CONFIDENCE_COUNT 条时，丢弃纯字面低置信证据，减少噪声。
HIGH_CONFIDENCE_SCORE = 3.0
MIN_HIGH_CONFIDENCE_COUNT = 2

SCOPE_BY_STAGE: dict[str, str] = {
    "01": "story_01_05",
    "02": "story_01_05",
    "03": "story_01_05",
    "04": "story_01_05",
    "05": "story_01_05",
    "06": "image_06",
    "07": "performance_07",
    "08": "camera_08",
}

_STATUS_STATEMENTS = {
    "ok": "已形成文件级证据：路径、行号、片段、命中词齐全，可进入确认流程。",
    "no_evidence": "元数据候选与有限正文回退扫描均未形成文件级证据：不得在创作阶段声称已调用本地知识库或已命中参考。",
    "no_candidates": "元数据未召回候选，有限正文回退也未命中：不得声称命中；可调整查询词、扩大 --fallback-files 或人工补充语料后重试。",
}


class KnowledgeServiceError(RuntimeError):
    pass


def _strip_quality(item: dict[str, Any]) -> dict[str, str]:
    """把内部带 quality 的命中还原为 knowledge-card 的 4 字段证据。"""
    return {key: item[key] for key in ("path", "page", "snippet", "hit")}


def _rank_evidence(
    items: list[dict[str, Any]], limit: int | None = None
) -> list[dict[str, Any]]:
    """按证据质量排序（同分时按路径/行号稳定排序），并去重。"""
    dedup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["path"], item["page"], item["hit"])
        current = dedup.get(key)
        if current is None or item["quality"]["score"] > current["quality"]["score"]:
            dedup[key] = item
    ordered = sorted(
        dedup.values(),
        key=lambda entry: (-entry["quality"]["score"], entry["path"], entry["page"]),
    )
    return ordered if limit is None else ordered[:limit]


def discover_kb_root() -> Path | None:
    """按 显式配置 → 环境变量 → 工作台配置 → 相邻目录探测 的顺序定位知识库根。"""
    env_root = os.environ.get("AI_FILM_KB_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.exists():
            return candidate
    if WORKBENCH_CONFIG.is_file():
        try:
            data = json.loads(WORKBENCH_CONFIG.read_text(encoding="utf-8"))
            root = str((data.get("knowledge") or {}).get("root") or "").strip()
            if root:
                candidate = Path(root).expanduser()
                if candidate.exists():
                    return candidate
        except (OSError, json.JSONDecodeError):
            pass
    bases = [Path.cwd(), REPO_ROOT.parent, REPO_ROOT.parent.parent]
    seen: set[Path] = set()
    for base in bases:
        if not base.is_dir():
            continue
        try:
            children = sorted(base.iterdir())
        except OSError:
            continue
        for child in children:
            if child in seen or not child.is_dir():
                continue
            seen.add(child)
            if (child / INDEX_DB_NAME).is_file():
                return child
    return None


def _normalize_queries(queries: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in queries:
        if isinstance(item, str):
            lane, separator, text = item.partition(":")
            if not separator:
                lane, text = "screenplay", item
            query: dict[str, Any] = {"lane": lane.strip(), "query": text.strip()}
        elif isinstance(item, dict):
            query = {
                "lane": str(item.get("lane") or "screenplay").strip(),
                "query": str(item.get("query") or "").strip(),
            }
            if item.get("weight") is not None:
                query["weight"] = float(item["weight"])
        else:
            raise KnowledgeServiceError(f"无法识别的查询项: {item!r}")
        if query["lane"] not in LANE_CATEGORIES:
            raise KnowledgeServiceError(
                f"未知检索通道 lane={query['lane']}；可选: {', '.join(LANE_CATEGORIES)}"
            )
        if not query["query"]:
            raise KnowledgeServiceError("查询词不能为空")
        normalized.append(query)
    return normalized


class KnowledgeService:
    def __init__(self, kb_root: str | Path | None = None):
        self.kb_root = Path(kb_root) if kb_root else None

    def health(self) -> dict[str, Any]:
        return {
            "service": "knowledge",
            "implemented": True,
            "mode": "read_only_recall_v2",
            "target_iteration": "2",
        }

    def probe(self) -> dict[str, Any]:
        root = self.kb_root or discover_kb_root()
        if root is None:
            raise KnowledgeServiceError(
                "未找到知识库索引 knowledgeIndex.sqlite。"
                "请用 --kb-root 指定知识库根目录，或设置 AI_FILM_KB_ROOT。"
            )
        try:
            return probe(root).to_dict()
        except AdapterError as exc:
            raise KnowledgeServiceError(str(exc)) from exc

    def search(
        self,
        project: str,
        stage: str,
        problem: str,
        queries: list[Any],
        candidates_limit: int = 40,
        evidence_limit: int = 8,
        max_hits_per_file: int = 2,
        fallback: bool = True,
        fallback_max_files: int = FALLBACK_MAX_FILES,
        fallback_max_bytes: int = FALLBACK_MAX_FILE_BYTES,
    ) -> dict[str, Any]:
        project = (project or "").strip()
        problem = (problem or "").strip()
        if not project:
            raise KnowledgeServiceError("project 不能为空")
        if stage not in SCOPE_BY_STAGE:
            raise KnowledgeServiceError(f"stage 必须是 01-08，收到: {stage!r}")
        if not problem:
            raise KnowledgeServiceError("problem 不能为空：证据卡必须绑定明确的待解问题")
        if candidates_limit <= 0:
            raise KnowledgeServiceError("candidates_limit 必须为正整数")
        if evidence_limit <= 0:
            raise KnowledgeServiceError("evidence_limit 必须为正整数")
        if fallback_max_files < 0:
            raise KnowledgeServiceError("fallback_max_files 不能为负数")
        if fallback_max_bytes <= 0:
            raise KnowledgeServiceError("fallback_max_bytes 必须为正整数")
        normalized = _normalize_queries(queries)
        if not normalized:
            raise KnowledgeServiceError("至少需要一个查询")

        root = self.kb_root or discover_kb_root()
        if root is None:
            raise KnowledgeServiceError("未找到知识库索引，无法检索")
        try:
            kb = probe(root)
        except AdapterError as exc:
            raise KnowledgeServiceError(str(exc)) from exc
        if kb.issues:
            raise KnowledgeServiceError("知识库当前不可用于只读适配: " + "；".join(kb.issues))

        terms: list[str] = []
        seen_terms: set[str] = set()
        for query in normalized:
            for term in query_terms(query["query"]):
                if term.casefold() not in seen_terms:
                    seen_terms.add(term.casefold())
                    terms.append(term)

        lanes = [query["lane"] for query in normalized]
        candidates, candidate_note = list_candidates(
            root,
            terms,
            lanes=lanes,
            limit=candidates_limit,
        )

        scored: list[dict[str, Any]] = []
        filtered_mis_hits = 0
        missing_files = 0
        scanned_paths: set[str] = set()
        collect_cap = evidence_limit * 3
        for candidate in candidates:
            hits, stats = scan_file_scored(
                root, candidate["path"], terms, max_hits=max_hits_per_file
            )
            scanned_paths.add(candidate["path"])
            if not hits and not (Path(root) / candidate["path"]).is_file():
                missing_files += 1
            scored.extend(hits)
            filtered_mis_hits += stats["filtered"]
            if len(scored) >= collect_cap:
                break

        lane_candidates = {lane: 0 for lane in lanes}
        for candidate in candidates:
            category = candidate.get("category", "")
            for lane in lanes:
                if category in LANE_CATEGORIES.get(lane, ()):
                    lane_candidates[lane] += 1

        fallback_report: dict[str, Any] = {
            "enabled": bool(fallback) and fallback_max_files > 0,
            "trigger": "",
            "files_listed": 0,
            "files_scanned": 0,
            "files_missing": 0,
            "hits": 0,
            "budget_files": fallback_max_files,
            "budget_bytes_per_file": fallback_max_bytes,
        }
        trigger = ""
        if len(scored) < evidence_limit:
            trigger = "evidence_below_limit"
        elif any(count == 0 for count in lane_candidates.values()):
            trigger = "lane_without_candidates"
        fallback_report["trigger"] = trigger

        merged_paths = [candidate["path"] for candidate in candidates]
        if fallback_report["enabled"] and trigger:
            listed = list_scan_files(root, lanes, limit=max(fallback_max_files * 2, fallback_max_files))
            fallback_report["files_listed"] = len(listed)
            extra_candidates: list[str] = []
            for item in listed:
                if fallback_report["files_scanned"] >= fallback_max_files:
                    break
                path = item["path"]
                if path in scanned_paths:
                    continue
                if not path.lower().endswith(EVIDENCE_EXTENSIONS):
                    continue
                if not (Path(root) / path).is_file():
                    fallback_report["files_missing"] += 1
                    continue
                fallback_report["files_scanned"] += 1
                hits, stats = scan_file_scored(
                    root,
                    path,
                    terms,
                    max_hits=max_hits_per_file,
                    max_bytes=fallback_max_bytes,
                )
                filtered_mis_hits += stats["filtered"]
                scanned_paths.add(path)
                if hits:
                    fallback_report["hits"] += len(hits)
                    scored.extend(hits)
                    extra_candidates.append(path)
                if len(scored) >= collect_cap:
                    break
            known = set(merged_paths)
            merged_paths.extend(path for path in extra_candidates if path not in known)
            if extra_candidates:
                candidate_note = (
                    candidate_note + "；" if candidate_note else ""
                ) + "元数据召回不足，已由有限正文回退扫描补足候选"

        all_ranked = _rank_evidence(scored)
        high_confidence = [
            item
            for item in all_ranked
            if item["quality"]["score"] >= HIGH_CONFIDENCE_SCORE
        ]
        use_high_only = len(high_confidence) >= MIN_HIGH_CONFIDENCE_COUNT
        ranked = (high_confidence if use_high_only else all_ranked)[:evidence_limit]
        dropped_low_confidence = (
            sum(
                1
                for item in all_ranked
                if item["quality"]["score"] < HIGH_CONFIDENCE_SCORE
            )
            if use_high_only
            else 0
        )
        evidence = [_strip_quality(item) for item in ranked]
        best_scores: dict[str, float] = {}
        for item in scored:
            best_scores[item["path"]] = max(
                best_scores.get(item["path"], 0.0), item["quality"]["score"]
            )
        ranked_paths = sorted(
            (path for path in merged_paths if path in best_scores),
            key=lambda path: (-best_scores[path], merged_paths.index(path)),
        )
        unranked_paths = [path for path in merged_paths if path not in best_scores]
        merged_paths = (ranked_paths + unranked_paths)[:candidates_limit]

        card: dict[str, Any] = {
            "contract_version": "1.0",
            "card_id": f"{project}-{stage}-{time.strftime('%Y%m%d-%H%M%S')}",
            "project": project,
            "stage": stage,
            "query_profile": {"problem": problem, "queries": normalized},
            "evidence": evidence,
            "candidates": merged_paths,
            "selected_documents": [],
            "deep_read_selected": False,
            "confirmed": {"by": "", "at": ""},
            "scope": [SCOPE_BY_STAGE[stage]],
        }
        contract_errors = validate(card, schema_name="knowledge-card")
        if contract_errors:
            raise KnowledgeServiceError(
                "内部 knowledge-card 契约校验失败: " + "; ".join(contract_errors)
            )

        status = "ok" if evidence else ("no_evidence" if merged_paths else "no_candidates")
        db_stat = Path(kb.db_path).stat()
        report: dict[str, Any] = {
            "status": status,
            "statement": _STATUS_STATEMENTS[status],
            "kb_root": kb.kb_root,
            "db_path": kb.db_path,
            "db_size_bytes": db_stat.st_size,
            "db_mtime_ns": db_stat.st_mtime_ns,
            "schema": kb.schema,
            "documents": kb.documents,
            "indexed_documents": kb.indexed_documents,
            "fts_external_supported": kb.fts_external_supported,
            "fts_note": kb.fts_note,
            "read_only": True,
            "lane_categories": {
                lane: list(LANE_CATEGORIES.get(lane, ())) for lane in set(lanes)
            },
            "lane_candidates": lane_candidates,
            "terms": terms,
            "candidates": len(merged_paths),
            "candidate_note": candidate_note,
            "evidence": len(evidence),
            "evidence_quality": {
                "considered": len(scored),
                "filtered_mis_hits": filtered_mis_hits,
                "phrase_hits": sum(1 for item in ranked if item["quality"]["phrase"]),
                "cooccurrence_hits": sum(
                    1 for item in ranked if item["quality"]["cooccurrence"]
                ),
                "top_score": ranked[0]["quality"]["score"] if ranked else 0,
                "high_confidence_evidence": len(high_confidence),
                "low_confidence_dropped": dropped_low_confidence,
                "sorted_by": "score",
            },
            "missing_files": missing_files,
            "fallback": fallback_report,
        }
        return {
            "ok": status == "ok",
            "status": status,
            "card": card,
            "report": report,
        }

    def retrieve(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """兼容占位接口；PoC 阶段等价于 search。"""
        return self.search(*args, **kwargs)
