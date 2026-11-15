"""文档链接检查（PRD §11.3-5）：Markdown 链接与行内代码里的仓库内路径必须存在。

用法:
    python scripts/check_doc_links.py [--root <仓库根>] [--json]
退出码: 0=全部存在，1=存在缺失引用。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_MD = ("README.md", "CHANGELOG.md")
DOCS_DIR = "docs"
TARGET_SUFFIXES = {
    ".md", ".json", ".py", ".ps1", ".command", ".csv", ".txt",
    ".yaml", ".yml", ".sh", ".html", ".svg", ".zip",
}
REPO_PREFIXES = (
    "docs/", "packages/", "scripts/", "tests/", "content/", "config/",
    "contracts/", "tools/", "dist/", "workbench.py",
)
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "//")
# 运行时目录（项目内生成，不属于仓库文件）
RUNTIME_PREFIXES = (
    "00_project/", "00_inbox/", "01_story/", "02_script/", "03_assets/",
    "04_performance/", "05_shots/", "06_prompts/", "07_generations/",
    "08_delivery/", ".workbench/",
)
# 构建产物目录（发行包在 build_release 后生成，文档可引用但不参与存在性检查）
GENERATED_PREFIXES = ("dist/",)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_RE = re.compile(r"`([^`\n]+)`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def iter_markdown(root: Path):
    for name in ROOT_MD:
        path = root / name
        if path.exists():
            yield path
    docs = root / DOCS_DIR
    if docs.is_dir():
        yield from sorted(docs.rglob("*.md"))


def _is_skipped_target(target: str) -> bool:
    raw = target.strip().strip("<>")
    if not raw or raw.startswith(SKIP_PREFIXES) or "://" in raw:
        return True
    if any(ch in raw for ch in "*<>{}$%~\\|="):
        return True
    if ":" in raw:  # 盘符、占位符
        return True
    if raw.startswith(RUNTIME_PREFIXES):
        return True
    if raw.startswith(GENERATED_PREFIXES):
        return True
    if raw.startswith("/"):  # API 路径（/api/...）等以斜杠开头的非仓库路径
        return True
    return False


def link_targets(line: str) -> list[str]:
    out = []
    for raw in LINK_RE.findall(line):
        target = raw.strip().strip("<>")
        if _is_skipped_target(target):
            continue
        target = target.split("#", 1)[0]
        if target:
            out.append(target)
    return out


def code_targets(line: str) -> list[str]:
    out = []
    for raw in CODE_RE.findall(line):
        text = raw.strip()
        if not text or " " in text or "\t" in text or len(text) > 160:
            continue
        if _is_skipped_target(text):
            continue
        is_repo_path = text.startswith(REPO_PREFIXES)
        if not is_repo_path:
            continue
        out.append(text)
    return out


def resolve(root: Path, md_path: Path, target: str) -> Path:
    if target.startswith("/"):
        return root / target.lstrip("/")
    for base in (md_path.parent, root):
        candidate = base / target
        if candidate.exists():
            return candidate
    return md_path.parent / target


def check(root: Path) -> tuple[int, list[dict[str, object]]]:
    checked = 0
    missing: list[dict[str, object]] = []
    for md_path in iter_markdown(root):
        lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
        in_fence = False
        for lineno, line in enumerate(lines, 1):
            if FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for target in link_targets(line) + code_targets(line):
                checked += 1
                if not resolve(root, md_path, target).exists():
                    missing.append({
                        "file": md_path.relative_to(root).as_posix(),
                        "line": lineno,
                        "target": target,
                    })
    return checked, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查文档中的仓库内路径引用是否存在")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    checked, missing = check(root)
    if args.json:
        print(json.dumps({"ok": not missing, "checked": checked, "missing": missing},
                         ensure_ascii=False, indent=2))
    else:
        print(f"文档链接检查：扫描 {checked} 处引用")
        for item in missing:
            print(f"MISSING {item['file']}:{item['line']} -> {item['target']}")
        print("全部引用存在" if not missing else f"缺失 {len(missing)} 处")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
