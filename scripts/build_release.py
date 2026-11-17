"""生成发行包：dist/workbench-<version>.zip + SHA256SUMS。

只打包仓库内受控文件（跳过 .git、缓存、临时目录、dist 自身）；
解压后目录根即 workbench/，可直接 `python workbench.py doctor`。
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
SKIP_DIRS = {".git", ".workbench", "__pycache__", ".idea", ".vscode", "dist", ".pytest_cache", "index", "storyboard-output"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
SKIP_SUFFIXES = {".tmp", ".bak", ".pyc", ".pyo"}


def version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def collect() -> list[Path]:
    files = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if rel.name in SKIP_FILES or rel.suffix in SKIP_SUFFIXES:
            continue
        files.append(rel)
    return files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build() -> int:
    ver = version()
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    archive = DIST_DIR / f"workbench-{ver}.zip"
    files = collect()
    if archive.exists():
        archive.unlink()
    # 固定时间戳/权限，保证同一份源码多次构建得到相同 SHA256（可复现构建，M20）。
    fixed_time = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            info = zipfile.ZipInfo(f"workbench/{rel.as_posix()}", date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, (REPO_ROOT / rel).read_bytes())
    digest = sha256_file(archive)
    sums = DIST_DIR / f"workbench-{ver}.sha256"
    sums.write_text(f"{digest}  workbench-{ver}.zip\n", encoding="utf-8")
    print(f"已生成 {archive}（{len(files)} 个文件，{archive.stat().st_size} 字节）")
    print(f"SHA256: {digest}")
    print(f"校验文件: {sums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
