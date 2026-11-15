"""发行包回滚演练（M18，PRD §11.4）。

验证「升级到最新发行包 → 回滚到上一版发行包」的交付链路可执行：
1. 解压上一版发行包，运行 `workbench.py version`；
2. 解压最新发行包覆盖，运行 version 应返回最新版；
3. 清空目录后重新解压上一版（回滚），version 应回到上一版。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
ZIP_RE = re.compile(r"^workbench-(\d+)\.(\d+)\.(\d+)\.zip$")


def find_release_zips(dist_dir: Path | str | None = None) -> list[Path]:
    """返回按版本升序排列的发行包。"""
    root = Path(dist_dir) if dist_dir else DIST_DIR
    if not root.is_dir():
        return []
    found: list[tuple[tuple[int, int, int], Path]] = []
    for path in root.glob("workbench-*.zip"):
        match = ZIP_RE.match(path.name)
        if match:
            found.append((tuple(int(part) for part in match.groups()), path))
    found.sort(key=lambda item: item[0])
    return [path for _, path in found]


def extract_zip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)


def run_version(root: Path) -> str:
    result = subprocess.run(
        [sys.executable, "workbench.py", "version"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        raise RuntimeError(f"version 执行失败（退出码 {result.returncode}）：{output}")
    return output


def drill(dist_dir: Path | str | None = None, *, workdir: Path | str | None = None) -> dict:
    """执行升级→回滚演练，返回步骤与版本结果。"""
    zips = find_release_zips(dist_dir)
    if len(zips) < 2:
        raise RuntimeError(f"至少需要两个发行包（dist 中找到 {len(zips)} 个）：{Path(dist_dir) if dist_dir else DIST_DIR}")
    previous, latest = zips[-2], zips[-1]
    base = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="wb_rollback_"))
    root = base / "workbench"

    def fresh_extract(zip_path: Path) -> None:
        if root.exists():
            shutil.rmtree(root)
        extract_zip(zip_path, base)
        if not (root / "workbench.py").is_file():
            raise RuntimeError(f"发行包缺少 workbench/workbench.py: {zip_path}")

    fresh_extract(previous)
    installed = run_version(root)

    fresh_extract(latest)
    upgraded = run_version(root)

    fresh_extract(previous)
    rolled_back = run_version(root)

    match_previous = ZIP_RE.match(previous.name)
    expected_previous = ".".join(match_previous.groups()) if match_previous else None
    report = {
        "ok": True,
        "dist_dir": str(Path(dist_dir) if dist_dir else DIST_DIR),
        "previous_zip": previous.name,
        "latest_zip": latest.name,
        "installed_version": installed,
        "upgraded_version": upgraded,
        "rolled_back_version": rolled_back,
        "workdir": str(base),
        "steps": [
            {"step": "install_previous", "zip": previous.name, "version": installed},
            {"step": "upgrade_latest", "zip": latest.name, "version": upgraded},
            {"step": "rollback_previous", "zip": previous.name, "version": rolled_back},
        ],
        "expected_previous_version": expected_previous or None,
    }
    report["ok"] = installed != upgraded and rolled_back == installed and bool(upgraded)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发行包升级/回滚演练")
    parser.add_argument("--dist", help="dist 目录（默认仓库 dist/）")
    parser.add_argument("--workdir", help="演练目录（默认临时目录）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--keep", action="store_true", help="保留演练目录（默认保留，便于人工复核）")
    args = parser.parse_args(argv)
    try:
        report = drill(args.dist, workdir=args.workdir)
    except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for step in report["steps"]:
            print(f"[OK] {step['step']}: {step['zip']} → {step['version']}")
        print(
            f"演练{'通过' if report['ok'] else '未通过'}："
            f"{report['previous_zip']} → {report['latest_zip']} → {report['previous_zip']}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
