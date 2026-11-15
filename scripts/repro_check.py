"""可复现构建检查（M20）。

连续构建两次发行包，要求：
1. 两次 zip 的 SHA256 完全相同（build_release 用固定时间戳/权限）；
2. 与 ``dist/workbench-<version>.sha256`` 记录的哈希一致。

用法::

    python scripts/repro_check.py
    python scripts/repro_check.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def build_once() -> str:
    completed = subprocess.run(
        [sys.executable, "scripts/build_release.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"构建失败：{completed.stderr.strip()[-500:]}")
    return sha256_file(DIST_DIR / f"workbench-{version()}.zip")


def recorded_hash() -> str:
    path = DIST_DIR / f"workbench-{version()}.sha256"
    if not path.is_file():
        return ""
    parts = path.read_text(encoding="utf-8").split()
    return parts[0] if parts else ""


def check() -> dict[str, object]:
    first = build_once()
    second = build_once()
    recorded = recorded_hash()
    return {
        "ok": first == second == recorded,
        "version": version(),
        "first": first,
        "second": second,
        "recorded": recorded,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="可复现构建检查")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    try:
        report = check()
    except Exception as exc:  # noqa: BLE001
        print(f"可复现构建检查失败: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"版本: {report['version']}")
        print(f"第一次构建: {report['first']}")
        print(f"第二次构建: {report['second']}")
        print(f"校验文件:   {report['recorded']}")
        print(f"结果: {'PASS（可复现）' if report['ok'] else 'FAIL（不可复现或校验不一致）'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
