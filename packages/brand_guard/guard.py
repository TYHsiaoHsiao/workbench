"""品牌守卫：扫描工作区与仓库中的禁用词，返回不含明文的命中报告。"""
from __future__ import annotations

import base64
import json
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

PACKAGES_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGES_ROOT.parent

OFFICE_EXTS = {".xlsx", ".docx", ".pptx"}
_DECODE_ORDERS = ("utf-8-sig", "utf-16", "gb18030")
# 归一化时剔除的分隔符：让字母间插入空格、连字符、下划线的写法同样命中。
_SEPARATORS = set(" \t\r\n_-·•.|/\\'\"`´‘’“”")


class BrandGuardError(RuntimeError):
    """词表、配置或扫描对象不可用时抛出。"""


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else REPO_ROOT / "config" / "brand-guard.json"
    if not path.is_file():
        raise BrandGuardError(f"找不到品牌守卫配置: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_wordlist(path: str | Path) -> list[str]:
    """从 base64 词表解码禁用词；仓库内不保存明文。"""
    wordlist_path = Path(path)
    if not wordlist_path.is_file():
        raise BrandGuardError(f"找不到品牌词表: {wordlist_path}")
    terms: list[str] = []
    for line in wordlist_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            terms.append(base64.b64decode(line).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:  # 词表损坏必须显式失败
            raise BrandGuardError(f"词表行无法解码: {exc}") from exc
    if not terms:
        raise BrandGuardError(f"词表为空: {wordlist_path}")
    return terms


def normalize(text: str) -> str:
    """NFKC + 大小写折叠 + 去分隔符，用于稳定的包含判断。"""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if ch not in _SEPARATORS and not ch.isspace())


def _decode_bytes(data: bytes) -> str | None:
    for encoding in _DECODE_ORDERS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _remove_safe_tokens(normalized_line: str, normalized_safe: list[str]) -> str:
    for token in normalized_safe:
        normalized_line = normalized_line.replace(token, "")
    return normalized_line


def scan_text(text: str, terms: list[str], rel_path: str,
              safe_tokens: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """逐行扫描文本；term 用 term#N 指代，避免报告泄露禁用词。

    safe_tokens 是显式允许的中性技术标识符（如外部数据格式名），扫描前先从
    归一化行中剔除，避免把外部 schema 名称误判为品牌。
    """
    hits: list[dict[str, Any]] = []
    normalized_terms = [(index, normalize(term)) for index, term in enumerate(terms, start=1)]
    normalized_safe = [normalize(token) for token in safe_tokens if token]
    for lineno, line in enumerate(text.splitlines(), start=1):
        normalized_line = _remove_safe_tokens(normalize(line), normalized_safe)
        if not normalized_line:
            continue
        for term_index, normalized_term in normalized_terms:
            if normalized_term and normalized_term in normalized_line:
                hits.append({"path": rel_path, "line": lineno, "term": f"term#{term_index}"})
                break
    return hits


def _scan_xml_zip(path: Path, terms: list[str], rel_path: str,
                  safe_tokens: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if not member.lower().endswith((".xml", ".rels", ".txt")):
                    continue
                raw = archive.read(member)
                text = _decode_bytes(raw)
                if text is None:
                    continue
                hits.extend(scan_text(text, terms, f"{rel_path}!{member}", safe_tokens))
    except (zipfile.BadZipFile, OSError) as exc:
        raise BrandGuardError(f"无法读取 Office 文件 {path}: {exc}") from exc
    return hits


def _skip_reason(path: Path, config: dict[str, Any]) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {ext.lower() for ext in config.get("skip_exts", [])}:
        return "skip_ext"
    max_mb = config.get("max_file_mb")
    if isinstance(max_mb, (int, float)):
        try:
            if path.stat().st_size > max_mb * 1024 * 1024:
                return "oversize"
        except OSError:
            return "unreadable"
    return None


def _under_any(path: Path, allowed_roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in allowed_roots)


def _load_allow_roots(config: dict[str, Any], repo_root: Path) -> list[Path]:
    allowlist_path = repo_root / config["allowlist"]
    if not allowlist_path.is_file():
        return []
    entries = json.loads(allowlist_path.read_text(encoding="utf-8")).get("entries", [])
    roots: list[Path] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("path"):
            roots.append((repo_root / entry["path"]).resolve())
    return roots


def _iter_files(target: Path, config: dict[str, Any], allowed_roots: list[Path]):
    if target.is_file():
        yield target
        return
    skip_dirs = set(config.get("skip_dirs", []))
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if parts & skip_dirs:
            continue
        if _under_any(path, allowed_roots):
            continue
        yield path


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def scan(repo_root: str | Path | None = None,
         config_path: str | Path | None = None) -> dict[str, Any]:
    """扫描 config targets 中的全部对象，返回可 JSON 序列化的报告。"""
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    config = load_config(config_path)
    terms = load_wordlist(root / config["wordlist"])
    allowed_roots = _load_allow_roots(config, root)
    safe_tokens = tuple(config.get("safe_tokens") or ())
    normalized_safe = [normalize(token) for token in safe_tokens if token]

    hits: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    scanned = 0
    missing_targets: list[str] = []
    targets_report: list[dict[str, Any]] = []

    for target in config.get("targets", []):
        target_path = (root / target["path"]).resolve()
        targets_report.append({"name": target.get("name", ""), "path": target["path"],
                               "exists": target_path.exists()})
        if not target_path.exists():
            missing_targets.append(target["path"])
            continue
        for file_path in _iter_files(target_path, config, allowed_roots):
            rel = _rel(file_path, root)
            if file_path.suffix.lower() in {".xlsx", ".docx", ".pptx"}:
                scanned += 1
                hits.extend(_scan_xml_zip(file_path, terms, rel, safe_tokens))
                continue
            reason = _skip_reason(file_path, config)
            if reason is not None:
                skipped.append({"path": rel, "reason": reason})
                continue
            text = _decode_bytes(file_path.read_bytes())
            if text is None:
                skipped.append({"path": rel, "reason": "binary"})
                continue
            scanned += 1
            hits.extend(scan_text(text, terms, rel, safe_tokens))
            normalized_name = _remove_safe_tokens(normalize(file_path.name), normalized_safe)
            for term_index, term in enumerate(terms, start=1):
                if normalize(term) and normalize(term) in normalized_name:
                    hits.append({"path": rel, "line": 0, "term": f"term#{term_index}"})
                    break

    return {
        "ok": not hits,
        "scanned": scanned,
        "hits": hits,
        "skipped": skipped,
        "missing_targets": missing_targets,
        "targets": targets_report,
    }
