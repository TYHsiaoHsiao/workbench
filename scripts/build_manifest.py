"""生成 manifest.json：记录发行文件清单与哈希，供安装器/升级校验。"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".workbench", "__pycache__", ".idea", ".vscode", "dist", ".pytest_cache", "index"}
SKIP_FILES = {"manifest.json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build() -> dict:
    files = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if relative.name in SKIP_FILES:
            continue
        files.append(
            {
                "path": relative.as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    version_file = REPO_ROOT / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "0.0.0"
    return {
        "version": version,
        "contract_version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "file_count": len(files),
        "files": files,
    }


def main() -> int:
    manifest = build()
    output = REPO_ROOT / "manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {output}（{manifest['file_count']} 个文件，版本 {manifest['version']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
