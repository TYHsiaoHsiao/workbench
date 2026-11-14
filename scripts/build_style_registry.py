"""构建 C 子系统导演风格注册表（只读扫描外部风格包，输出元数据快照）。

用法：
  python scripts/build_style_registry.py [--root <风格包根目录>] [--out content/style-registry.json]
                                         [--report docs/style-registry-report.md]

风格包根目录的判定顺序：
  1. --root
  2. 环境变量 AI_FILM_STYLE_PACK_ROOT
  3. 仓库同级目录中同时包含 SKILL.md 与 10 个 NN_ 分类目录的目录

脚本不复制任何图片二进制，只记录路径、调色板、文案与质量标记。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = REPO_ROOT / "packages"
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from contracts import validate  # noqa: E402

CATEGORY_RE = re.compile(r"^([0-9]{2})_(.+)$")
DIRECTOR_RE = re.compile(r"^([0-9]{3})[_ ]+(.+)$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
PROMPT_FILES = {
    "midjourney": "midjourney_prompts.md",
    "conversational": "conversational_prompts.md",
    "video": "video_prompts.md",
    "stable_diffusion": "stable_diffusion_prompts.md",
}
PROFILE_KEYS = ("definition", "lighting", "framing", "grading", "avoid")


def guess_root() -> Path:
    env = os.environ.get("AI_FILM_STYLE_PACK_ROOT")
    if env:
        return Path(env)
    parent = REPO_ROOT.parent
    if parent.is_dir():
        for child in sorted(parent.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").exists():
                continue
            cats = [p for p in child.iterdir() if p.is_dir() and CATEGORY_RE.match(p.name)]
            if len(cats) >= 10:
                return child
    raise SystemExit("未找到风格包根目录，请用 --root 或 AI_FILM_STYLE_PACK_ROOT 指定")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def count_lines(path: Path) -> int:
    text = read_text(path)
    if not text:
        return 0
    return len(text.splitlines())


def parse_director(dirname: str) -> tuple[str | None, str, str]:
    """返回 (编号, 英文名, 中文名)。无法解析时编号为 None。"""
    m = DIRECTOR_RE.match(dirname)
    if not m:
        return None, dirname, ""
    number, rest = m.group(1), m.group(2).strip()
    parts = [p.strip() for p in rest.split("_") if p.strip()]
    zh = ""
    if len(parts) >= 2 and CJK_RE.search(parts[-1]):
        zh = parts[-1]
        parts = parts[:-1]
    return number, " ".join(parts), zh


def has_combining_marks(text: str) -> bool:
    return any(unicodedata.category(ch) == "Mn" for ch in text)


def normalize_ratio(value) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    if num <= 1.0:
        num *= 100.0
    return round(num, 2)


def load_palette(director_dir: Path) -> tuple[dict | None, list[str]]:
    issues: list[str] = []
    path = director_dir / "assets" / "color_palettes" / "palette.json"
    if not path.exists():
        return None, ["missing_palette_json"]
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return None, ["invalid_palette_json"]
    palette = data.get("palette") if isinstance(data, dict) else None
    if not isinstance(palette, dict):
        return None, ["invalid_palette_structure"]
    primary_raw = palette.get("primary") or []
    emotional_raw = palette.get("emotional") or []
    primary = []
    for item in primary_raw:
        if not isinstance(item, dict):
            continue
        hex_value = item.get("hex", "")
        if not HEX_RE.match(str(hex_value)):
            issues.append("invalid_hex")
            hex_value = "#000000"
        primary.append({
            "code": str(item.get("code", "")),
            "hex": str(hex_value).upper(),
            "name_zh": str(item.get("name_zh", "")),
            "ratio": normalize_ratio(item.get("ratio", 0)),
        })
    emotional = []
    for item in emotional_raw:
        if not isinstance(item, dict):
            continue
        hex_value = item.get("hex", "")
        if not HEX_RE.match(str(hex_value)):
            issues.append("invalid_hex")
            hex_value = "#000000"
        emotional.append({
            "code": str(item.get("code", "")),
            "hex": str(hex_value).upper(),
            "name_zh": str(item.get("name_zh", "")),
            "emotion": str(item.get("emotion", "")),
        })
    if len(primary) != 6:
        issues.append(f"primary_count_{len(primary)}")
    if len(emotional) != 4:
        issues.append(f"emotional_count_{len(emotional)}")
    ratio_sum = round(sum(p["ratio"] for p in primary), 2)
    if primary and abs(ratio_sum - 100.0) > 0.5:
        issues.append(f"primary_ratio_sum_{ratio_sum:g}")
    profile = data.get("style_profile") if isinstance(data, dict) else None
    style_profile = {}
    if isinstance(profile, dict):
        for key in PROFILE_KEYS:
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                style_profile[key] = value.strip()
    keywords_raw = {}
    for key in ("composition_keywords", "color_keywords", "mood_keywords"):
        values = data.get(key) if isinstance(data, dict) else None
        if isinstance(values, list):
            keywords_raw[key] = [str(v) for v in values if isinstance(v, str)]
    lighting = data.get("lighting") if isinstance(data, dict) else None
    extracted = {
        "primary": primary,
        "emotional": emotional,
        "primary_ratio_sum": ratio_sum,
    }
    meta = {
        "director": data.get("director") if isinstance(data.get("director"), dict) else {},
        "lighting": lighting if isinstance(lighting, dict) else {},
        "style_profile": style_profile,
        "keywords": {
            "composition": keywords_raw.get("composition_keywords", []),
            "color": keywords_raw.get("color_keywords", []),
            "mood": keywords_raw.get("mood_keywords", []),
        },
    }
    return {"palette": extracted, "meta": meta}, issues


def scan_color_card(director_dir: Path) -> dict:
    card = director_dir / "色卡主文档.md"
    result = {"exists": card.exists(), "copyright": False, "image_links": 0, "broken_image_links": 0}
    if not card.exists():
        return result
    text = read_text(card)
    low = text.lower()
    result["copyright"] = ("版权" in text) or ("©" in text) or ("copyright" in low) or ("仅供学习" in text)
    for target in IMAGE_RE.findall(text):
        raw = target.strip().split(" ", 1)[0]
        if raw.startswith(("http://", "https://", "data:")):
            continue
        result["image_links"] += 1
        candidate = (director_dir / raw.replace("\\", "/")).resolve()
        try:
            candidate.relative_to(director_dir.resolve())
        except ValueError:
            result["broken_image_links"] += 1
            continue
        if not candidate.exists():
            result["broken_image_links"] += 1
    return result


def scan_references_meta(director_dir: Path) -> dict:
    """来源说明与可移植性标记：不复制旧绝对路径内容，只标记风险。"""
    ref_dir = director_dir / "assets" / "references"
    if not ref_dir.is_dir():
        ref_dir = director_dir / "references"
    meta = {"has_sources": False, "old_absolute_path": False, "files": 0}
    if not ref_dir.is_dir():
        return meta
    for path in ref_dir.rglob("*"):
        if not path.is_file():
            continue
        meta["files"] += 1
        name = path.name.lower()
        text = ""
        if name.endswith((".md", ".json", ".txt")):
            text = read_text(path)
        if "reference_sources" in name and text.strip():
            meta["has_sources"] = True
        if ("\\" + "雷龙飞") in text or re.search(r"[A-Za-z]:\\\\", text):
            meta["old_absolute_path"] = True
    return meta


def build_entry(category_id: str, category_name: str, category_dir: Path, director_dir: Path) -> dict | None:
    number, name_en, name_zh = parse_director(director_dir.name)
    issues: list[str] = []
    if number is None:
        return None
    if " " in name_en:
        issues.append("dir_name_space")
    if has_combining_marks(director_dir.name) or unicodedata.normalize("NFC", director_dir.name) != director_dir.name:
        issues.append("dir_name_unicode")
    if name_en.endswith(" 等") or name_zh.endswith(" 等"):
        issues.append("dir_name_suffix")
    palette_data, palette_issues = load_palette(director_dir)
    issues.extend(palette_issues)
    palette = palette_data["palette"] if palette_data else None
    meta = palette_data["meta"] if palette_data else {}
    card = scan_color_card(director_dir)
    ref_meta = scan_references_meta(director_dir)
    prompts = {}
    prompt_missing = []
    for key, filename in PROMPT_FILES.items():
        path = director_dir / "prompts" / filename
        prompts[key] = count_lines(path) if path.exists() else 0
        if not path.exists():
            prompt_missing.append(f"missing_prompt_{key}")
    issues.extend(prompt_missing)
    references_dir = director_dir / "assets" / "references"
    if not references_dir.is_dir():
        references_dir = director_dir / "references"
    references_count = ref_meta["files"]
    if references_count == 0:
        issues.append("missing_references")
    if not card["exists"]:
        issues.append("missing_color_card")
    if card["broken_image_links"]:
        issues.append(f"broken_image_links_{card['broken_image_links']}")
    if not ref_meta["has_sources"] and not card["copyright"]:
        issues.append("missing_sources_note")
    if ref_meta["old_absolute_path"]:
        issues.append("manifest_old_absolute_path")
    style_profile = meta.get("style_profile") or {}
    profile_complete = all(style_profile.get(k) for k in PROFILE_KEYS)
    if not profile_complete:
        issues.append("incomplete_style_profile")
    prompts_present = sum(1 for v in prompts.values() if v > 0)
    has_palette = palette is not None
    if has_palette and card["exists"] and prompts_present == 4 and profile_complete:
        grade = "A"
    elif has_palette and card["exists"] and prompts_present >= 2:
        grade = "B"
    else:
        grade = "C"
    safety_prefix = tuple(i.split("_")[0] for i in issues)
    hard_issues = sum(1 for i in safety_prefix if i in {"missing_palette_json", "invalid_palette_json", "invalid_palette_structure",
                                                         "missing_color_card", "invalid_hex"})
    if grade == "A" and hard_issues:
        grade = "B"
    risk_issues = {"missing_references"}
    has_risks = any(i in risk_issues or i.startswith(("dir_name_", "broken_image_links_")) for i in issues)
    if grade == "A" and has_risks:
        grade = "B"
    entry = {
        "id": number,
        "name_en": name_en,
        "name_zh": name_zh,
        "directory": f"{category_dir.name}/{director_dir.name}",
        "category": category_id,
        "category_name": category_name,
        "nationality": str((meta.get("director") or {}).get("nationality", "")),
        "prompts": prompts,
        "references_count": references_count,
        "quality": grade,
        "issues": sorted(set(issues)),
        "flags": {
            "has_palette_json": has_palette,
            "has_color_card": card["exists"],
            "has_prompt_files": prompts_present == 4,
            "has_references": references_count > 0,
            "has_copyright_note": bool(card["copyright"] or ref_meta["has_sources"]),
            "broken_image_links": card["broken_image_links"],
        },
    }
    if palette:
        entry["palette"] = palette
    if style_profile:
        entry["style_profile"] = style_profile
    if meta.get("keywords"):
        entry["keywords"] = meta["keywords"]
    return entry


def build_registry(root: Path) -> dict:
    categories = []
    entries = []
    skipped = []
    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir():
            continue
        m = CATEGORY_RE.match(cat_dir.name)
        if not m:
            continue
        category_id, category_name = m.group(1), m.group(2)
        count = 0
        for director_dir in sorted(cat_dir.iterdir()):
            if not director_dir.is_dir():
                continue
            entry = build_entry(category_id, category_name, cat_dir, director_dir)
            if entry is None:
                skipped.append(director_dir.name)
                continue
            entries.append(entry)
            count += 1
        categories.append({
            "id": category_id,
            "name": category_name,
            "directory": cat_dir.name,
            "count": count,
        })
    entries.sort(key=lambda e: e["id"])
    grade_counts = {"A": 0, "B": 0, "C": 0}
    issue_counts: dict[str, int] = {}
    palette_groups: dict[str, list[str]] = {}
    for entry in entries:
        grade_counts[entry["quality"]] += 1
        for issue in entry["issues"]:
            key = issue.rsplit("_", 1)[0] if issue.startswith("broken_image_links_") else issue
            issue_counts[key] = issue_counts.get(key, 0) + 1
        primary = (entry.get("palette") or {}).get("primary") or []
        if primary:
            digest = hashlib.sha256("|".join(p["hex"] for p in primary).encode("utf-8")).hexdigest()
            palette_groups.setdefault(digest, []).append(entry["id"])
    duplicates = [ids for ids in palette_groups.values() if len(ids) > 1]
    registry = {
        "contract_version": "1.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "root_name": root.name,
            "root_path": str(root),
            "directors": len(entries),
            "categories": len(categories),
            "note": "元数据快照，不含图片二进制；图片仍由外部风格包提供。",
        },
        "categories": categories,
        "entries": entries,
        "qc": {
            "grade_counts": grade_counts,
            "issue_counts": dict(sorted(issue_counts.items())),
            "duplicate_palettes": sum(len(ids) for ids in duplicates),
            "duplicate_palette_groups": len(duplicates),
        },
    }
    if skipped:
        registry["qc"]["skipped_directories"] = skipped
    return registry


def write_report(registry: dict, report_path: Path, root: Path) -> None:
    qc = registry["qc"]
    lines = [
        "# 风格注册表构建报告",
        "",
        f"- 风格包根目录：`{root}`",
        f"- 构建时间：{registry['generated_at']}",
        f"- 导演条目：{len(registry['entries'])}；分类：{len(registry['categories'])}",
        f"- 质量分级：A {qc['grade_counts']['A']} / B {qc['grade_counts']['B']} / C {qc['grade_counts']['C']}",
        f"- 重复调色板：{qc['duplicate_palette_groups']} 组、{qc['duplicate_palettes']} 条",
        "",
        "## 问题统计",
        "",
        "| 问题 | 条目数 |",
        "|---|---|",
    ]
    for issue, count in qc["issue_counts"].items():
        lines.append(f"| `{issue}` | {count} |")
    lines += ["", "## 分类覆盖", "", "| 编号 | 分类 | 条目 |", "|---|---|---|"]
    for cat in registry["categories"]:
        lines.append(f"| {cat['id']} | {cat['name']} | {cat['count']} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建导演风格注册表（只读扫描，不复制二进制）")
    parser.add_argument("--root", help="风格包根目录")
    parser.add_argument("--out", default="content/style-registry.json", help="输出 JSON（相对仓库根）")
    parser.add_argument("--report", help="可选：输出 Markdown 报告路径（相对仓库根）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else guess_root().resolve()
    if not root.is_dir():
        print(f"根目录不存在：{root}", file=sys.stderr)
        return 1
    registry = build_registry(root)
    errors = validate(registry, schema_name="style-registry.schema.json")
    if errors:
        print("注册表未通过契约校验：", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    out = (REPO_ROOT / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.report:
        report = (REPO_ROOT / args.report).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        write_report(registry, report, root)
    summary = {
        "entries": len(registry["entries"]),
        "categories": len(registry["categories"]),
        "grade_counts": registry["qc"]["grade_counts"],
        "duplicate_palette_groups": registry["qc"]["duplicate_palette_groups"],
        "out": str(out),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
