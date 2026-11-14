"""意图路由：把用户一句话分类为维护口令 / 知识库调用 / 阶段指令 / 入口 / 修订。

关键约束：
- 维护口令（配置/更新知识库、整理新剧本、升级工程规则）必须隔离，永不进入创作阶段；
- 知识库调用必须由用户明确触发，路由只做识别，不主动检索；
- 入口 A/B/C/D 只在首次确认，路由只做候选识别。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core_router.registry import REPO_ROOT

INTENT_RULES = REPO_ROOT / "content" / "intent-rules.json"

INTENT_KINDS = (
    "maintenance",
    "knowledge",
    "direct_entry",
    "stage",
    "entry",
    "revision",
    "unknown",
)


class IntentError(ValueError):
    """规则文件缺失或不合法时抛出。"""


def normalize(text: str) -> str:
    """去掉空白，ASCII 转小写，便于中文包含匹配。"""
    return re.sub(r"\s+", "", text or "").lower()


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    rules_path = Path(path) if path is not None else INTENT_RULES
    try:
        with rules_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise IntentError(f"意图规则不可用: {rules_path}: {exc}") from exc


def _match_terms(text: str, terms: list[str]) -> str | None:
    for term in terms:
        if normalize(term) and normalize(term) in text:
            return term
    return None


def _match_mapping(text: str, mapping: dict[str, list[str]]) -> tuple[str | None, str | None]:
    # 长词优先，避免「从零」抢在「从零开始」之前命中。
    candidates: list[tuple[int, str, str]] = []
    for key, terms in mapping.items():
        for term in terms:
            needle = normalize(term)
            if needle and needle in text:
                candidates.append((len(needle), key, term))
    if not candidates:
        return None, None
    candidates.sort(reverse=True)
    return candidates[0][1], candidates[0][2]


def classify(text: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回意图字典（可直接 JSON 输出）。"""
    rules = rules or load_rules()
    text = text or ""
    norm = normalize(text)

    def result(kind: str, matched: str | None, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": kind,
            "matched": matched or "",
            "is_maintenance": kind == "maintenance",
            "requires_confirmation": kind in ("maintenance", "knowledge", "direct_entry"),
        }
        payload.update(extra)
        return payload
    # 1) 维护口令优先：即使同时出现其他关键词，也绝不进入创作。
    command, term = _match_mapping(norm, rules.get("maintenance", {}))
    if command:
        return result("maintenance", term, command=command,
                      note="知识库/工程维护口令：直接交维护流程，不进入创作阶段")

    # 2) 知识库主动调用。
    term = _match_terms(norm, rules.get("knowledge_triggers", []))
    if term:
        return result("knowledge", term,
                      command="knowledge_retrieve",
                      note="用户明确调用本地知识库；由知识服务生成候选卡，等待确认")

    # 3) 直接入口（整场跳过前序）。
    stage, term = _match_mapping(norm, rules.get("direct_entries", {}))
    if stage:
        return result("direct_entry", term, stage=stage,
                      note=f"直接进入阶段 {stage}；缺生产资料时先做接管检查")

    # 4) 修订/回退：必须先于阶段识别，避免「回到剧本阶段…」被当成普通阶段指令。
    term = _match_terms(norm, rules.get("revision", []))
    if term:
        return result("revision", term,
                      note="修订/回退：先写新版本，再标记受影响下游")

    # 5) 阶段指令。
    stage, term = _match_mapping(norm, rules.get("stages", {}))
    if stage:
        return result("stage", term, stage=stage, note=f"指定阶段 {stage}")

    # 6) 入口候选。
    entry, term = _match_mapping(norm, rules.get("entries", {}))
    if entry:
        return result("entry", term, entry=entry,
                      note=f"入口候选 {entry}；本轮只确认一次")

    return result("unknown", None, note="未识别到明确意图；应先确认入口或当前阶段")


def route(text: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """classify 的别名，语义更贴近路由。"""
    return classify(text, rules)
