"""文件级证据：在候选文件内定位命中词、行号与片段，供 knowledge-card 使用。

只读；路径必须位于知识库根目录之下；仅扫描 Markdown / TXT 文本。

v0.3.1 起增加轻量证据质量：
- 过滤明确动作/物件误命中（如「反转身倚在窗边」「把宣传册反转过来」）；
- 结构语境词与常见叙事搭配加权；
- 多查询词共现加权。
评分用于排序与报告，不写入 knowledge-card（契约保持 4 字段不变）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

EVIDENCE_EXTENSIONS = (".md", ".txt")
MAX_EVIDENCE_FILE_BYTES = 8 * 1024 * 1024
MAX_SNIPPET_CHARS = 180

# 结构语境词：出现时说明该行更可能在讨论叙事/剧本，而非动作或物件。
STRUCTURAL_HINTS = (
    "情节",
    "剧情",
    "故事",
    "结局",
    "身份",
    "真相",
    "伏笔",
    "铺垫",
    "高潮",
    "转折",
    "结构",
    "叙事",
    "剧本",
    "角色",
    "人物",
    "冲突",
    "悬念",
    "动机",
    "第三幕",
    "第二幕",
    "第一幕",
)

# 明确的动作/物件误命中模式（命中区间落在这些模式内即过滤）。
MIS_HIT_PATTERN = re.compile(
    r"(反转身|反转过来|反转过去|反转身体|反转头|反转手|反转脸|反转脚|反转方向)"
)

# 常见叙事搭配：整行出现时加权。
PHRASE_PATTERNS = (
    "反转设计",
    "情节反转",
    "剧情反转",
    "身份反转",
    "结局反转",
    "反转点",
    "反转结构",
    "反转手法",
    "反转桥段",
    "反转伏笔",
    "核心事件",
)


class EvidenceError(RuntimeError):
    pass


def resolve_under(root: Path | str, rel_path: str) -> Path:
    """把库内相对路径解析为绝对路径，并阻止越界访问。"""
    base = Path(root).resolve()
    target = (base / rel_path).resolve()
    if target != base and base not in target.parents:
        raise EvidenceError(f"越界路径，拒绝读取: {rel_path}")
    return target


def _is_mis_hit(line: str, index: int, term: str) -> bool:
    """判断某次命中是否属于动作/物件语境（如「反转身」）。"""
    for match in MIS_HIT_PATTERN.finditer(line):
        if match.start() <= index < match.end():
            return True
    return False


def _score_line(line: str, ordered_terms: list[str]) -> tuple[list[str], dict[str, Any]]:
    """为一行的命中计算质量；返回 (有效命中词, 质量明细)。"""
    accepted: list[str] = []
    filtered = 0
    for term in ordered_terms:
        cursor = line.find(term)
        accepted_term = False
        while cursor >= 0:
            if _is_mis_hit(line, cursor, term):
                filtered += 1
            else:
                accepted_term = True
                break
            cursor = line.find(term, cursor + 1)
        if accepted_term:
            accepted.append(term)
    phrase = any(pattern in line for pattern in PHRASE_PATTERNS)
    hint = any(word in line for word in STRUCTURAL_HINTS)
    cooccurrence = len(accepted) >= 2
    score = float(len(accepted))
    if accepted and phrase:
        score += 4.0
    if accepted and hint:
        score += 2.0
    if cooccurrence:
        score += 3.0
    return accepted, {
        "score": score,
        "matched_terms": accepted,
        "filtered": filtered,
        "phrase": bool(accepted) and phrase,
        "hint": bool(accepted) and hint,
        "cooccurrence": cooccurrence,
    }


def scan_file_scored(
    root: Path | str,
    rel_path: str,
    terms: list[str],
    max_hits: int = 2,
    max_bytes: int = MAX_EVIDENCE_FILE_BYTES,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """返回 (命中列表, 统计)；命中列表项含 quality 字段，供内部排序使用。"""
    stats = {"filtered": 0}
    if not terms or max_hits <= 0:
        return [], stats
    try:
        target = resolve_under(root, rel_path)
    except EvidenceError:
        return [], stats
    if not target.is_file():
        return [], stats
    if target.suffix.lower() not in EVIDENCE_EXTENSIONS:
        return [], stats
    try:
        size = target.stat().st_size
        if size <= 0:
            return [], stats
        read_bytes = min(size, max(0, int(max_bytes)))
        if read_bytes <= 0:
            return [], stats
        with target.open("rb") as handle:
            data = handle.read(read_bytes)
        text = data.decode("utf-8", errors="replace")
    except OSError:
        return [], stats

    ordered = sorted({term for term in terms if len(term) >= 2}, key=len, reverse=True)
    if not ordered:
        return [], stats

    hits: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        matched_terms, quality = _score_line(line, ordered)
        stats["filtered"] += int(quality["filtered"])
        if not matched_terms:
            continue
        # 选取最长的有效命中词作为 hit，并用它的位置截取片段。
        hit = next((term for term in ordered if term in matched_terms), ordered[0])
        index = line.find(hit)
        start = max(0, index - 40)
        end = min(len(line), index + len(hit) + 80)
        snippet = line[start:end].strip()[:MAX_SNIPPET_CHARS]
        if not snippet:
            continue
        if start > 0:
            snippet = "…" + snippet
        if end < len(line):
            snippet = snippet + "…"
        hits.append(
            {
                "path": rel_path.replace("\\", "/"),
                "page": f"行 {lineno}",
                "snippet": snippet,
                "hit": hit,
                "quality": quality,
            }
        )
        if len(hits) >= max_hits:
            break
    return hits, stats


def scan_file(
    root: Path | str,
    rel_path: str,
    terms: list[str],
    max_hits: int = 2,
    max_bytes: int = MAX_EVIDENCE_FILE_BYTES,
) -> list[dict[str, str]]:
    """返回 [{path,page,snippet,hit}]；无法读取或未命中时返回空列表。

    `max_bytes` 为单文件读取上限（回退扫描用较小值控制总成本），默认 8MB。
    """
    hits, _ = scan_file_scored(root, rel_path, terms, max_hits=max_hits, max_bytes=max_bytes)
    return [
        {key: item[key] for key in ("path", "page", "snippet", "hit")}  # type: ignore[dict-item]
        for item in hits
    ]
