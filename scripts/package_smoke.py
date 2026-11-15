"""发行包冒烟（PRD §11.3-4 / §11.4）：SHA256 校验 -> 解压到临时目录 -> version/doctor。

用法:
    python scripts/package_smoke.py [--zip dist/workbench-2.5.0.zip] [--json]
退出码: 0=冒烟通过，1=失败。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_latest_zip(dist_dir: Path | None = None) -> Path | None:
    dist = Path(dist_dir or DIST_DIR)
    if not dist.is_dir():
        return None
    candidates = sorted(dist.glob("workbench-*.zip"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def verify_sha(zip_path: Path) -> tuple[bool, str]:
    sums = zip_path.with_suffix(".sha256")
    if not sums.exists():
        return False, f"缺少校验文件 {sums.name}"
    parts = sums.read_text(encoding="utf-8").strip().split()
    if not parts:
        return False, f"校验文件为空：{sums.name}"
    expected = parts[0].lower()
    actual = sha256_file(zip_path)
    ok = expected == actual
    return ok, f"expected {expected[:16]}… actual {actual[:16]}…"


def extract_zip(zip_path: Path, dest: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    for candidate in sorted(Path(dest).iterdir()):
        if candidate.is_dir() and (candidate / "workbench.py").exists():
            return candidate
    raise RuntimeError("解压后未找到 workbench/workbench.py")


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)


def smoke(zip_path: Path) -> dict:
    report: dict = {
        "zip": zip_path.name,
        "ok": False,
        "files": None,
        "version": None,
        "steps": [],
    }
    ok_sha, detail = verify_sha(zip_path)
    report["steps"].append({"name": "sha256", "ok": ok_sha, "detail": detail})
    if not ok_sha:
        report["error"] = detail
        return report
    with zipfile.ZipFile(zip_path) as zf:
        report["files"] = len(zf.namelist())

    tmp_dir = Path(tempfile.mkdtemp(prefix="wb_pkg_"))
    try:
        root = extract_zip(zip_path, tmp_dir)
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
        report["version"] = version

        result = _run([sys.executable, "workbench.py", "version"], root)
        ok_version = result.returncode == 0 and version in result.stdout and "contracts" in result.stdout
        report["steps"].append({
            "name": "version",
            "ok": ok_version,
            "detail": (result.stdout or result.stderr).strip()[:200],
        })

        result = _run([sys.executable, "workbench.py", "doctor"], root)
        output = result.stdout or ""
        ok_doctor = result.returncode == 0 and "[FAIL]" not in output
        tail = output.strip().splitlines()[-1][:200] if output.strip() else ""
        report["steps"].append({"name": "doctor", "ok": ok_doctor, "detail": tail})

        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            ok_manifest = data.get("version") == version
            report["steps"].append({
                "name": "manifest",
                "ok": ok_manifest,
                "detail": f"manifest version={data.get('version')}",
            })
        report["ok"] = all(step["ok"] for step in report["steps"])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发行包冒烟：SHA256 + 解压 + version/doctor")
    parser.add_argument("--zip", default=None, help="指定发行包路径，缺省取 dist 下最新 zip")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    zip_path = Path(args.zip) if args.zip else find_latest_zip()
    if zip_path is None or not zip_path.exists():
        print("未找到发行包：请先运行 python scripts/build_release.py")
        return 1
    report = smoke(zip_path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for step in report["steps"]:
            print(f"[{'OK' if step['ok'] else 'FAIL'}] {step['name']}: {step['detail']}")
        print(f"发行包冒烟：{'通过' if report['ok'] else '失败'}（{zip_path.name}，{report['files']} 个文件）")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
