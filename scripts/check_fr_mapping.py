"""需求追溯检查（M19）：`docs/requirements-traceability.md` 必须覆盖 PRD §6 全部 FR。

CI 与本地均可运行：
    python scripts/check_fr_mapping.py [--root <仓库>] [--prd <PRD 路径>] [--json]

规则：
- 追溯表必须覆盖 FR-01–FR-22，且每条恰好出现一次（表格首列 `| FR-xx ...`）。
- 若提供 PRD（默认尝试仓库上一级 `AI影视工作台开发PRD.md`），则追溯表与 PRD §6 标题集合必须一致。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_FR = tuple(f"FR-{i:02d}" for i in range(1, 23))
TRACE_FILE = "docs/requirements-traceability.md"
FR_ROW_RE = re.compile(r"^\|\s*(FR-\d{2})\b", re.MULTILINE)
PRD_HEADING_RE = re.compile(r"^###\s+(FR-\d{2})\b", re.MULTILINE)
DEFAULT_PRD_NAME = "AI影视工作台开发PRD.md"


def extract_ids(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [match.group(1) for match in pattern.finditer(text)]


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def check(root: str | Path, prd: str | Path | None = None) -> dict:
    root = Path(root)
    trace_path = root / TRACE_FILE
    report: dict = {
        "ok": False,
        "trace_file": str(trace_path),
        "expected": list(EXPECTED_FR),
        "found": [],
        "missing": [],
        "duplicates": [],
        "extra": [],
        "prd_path": None,
        "prd_missing": None,
        "prd_extra": None,
    }
    if not trace_path.exists():
        report["error"] = f"缺少追溯表 {TRACE_FILE}"
        return report
    ids = extract_ids(trace_path.read_text(encoding="utf-8"), FR_ROW_RE)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    missing = [fr for fr in EXPECTED_FR if fr not in ids]
    extra = [value for value in _dedupe(ids) if value not in EXPECTED_FR]
    report.update(
        ok=not missing and not duplicates and not extra,
        found=list(dict.fromkeys(ids)),
        missing=missing,
        duplicates=duplicates,
        extra=extra,
    )

    if prd is None:
        candidate = root.parent / DEFAULT_PRD_NAME
        if candidate.exists():
            prd = candidate
    if prd is not None:
        prd_path = Path(prd)
        if prd_path.exists():
            prd_ids = extract_ids(prd_path.read_text(encoding="utf-8"), PRD_HEADING_RE)
            prd_missing = [value for value in prd_ids if value not in ids]
            prd_extra = [value for value in ids if value not in prd_ids]
            report.update(
                prd_path=str(prd_path),
                prd_missing=prd_missing,
                prd_extra=prd_extra,
            )
            if prd_missing or prd_extra:
                report["ok"] = False
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 PRD FR ↔ 需求追溯表映射")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="仓库根目录")
    parser.add_argument("--prd", default=None, help="PRD 路径（默认尝试仓库上一级）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args(argv)

    report = check(args.root, args.prd)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"追溯表：{report['trace_file']}")
        print(f"覆盖：{len(report['found'])}/{len(EXPECTED_FR)} 条 FR")
        if report.get("error"):
            print(f"[FAIL] {report['error']}")
        if report["missing"]:
            print(f"[FAIL] 缺少 FR：{', '.join(report['missing'])}")
        if report["duplicates"]:
            print(f"[FAIL] 重复 FR：{', '.join(report['duplicates'])}")
        if report["extra"]:
            print(f"[FAIL] 非预期 FR：{', '.join(report['extra'])}")
        if report.get("prd_path"):
            print(f"PRD：{report['prd_path']}")
            if report.get("prd_missing"):
                print(f"[FAIL] PRD 有、追溯表缺：{', '.join(report['prd_missing'])}")
            if report.get("prd_extra"):
                print(f"[FAIL] 追溯表有、PRD 缺：{', '.join(report['prd_extra'])}")
        print("映射检查通过。" if report["ok"] else "映射检查未通过。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
