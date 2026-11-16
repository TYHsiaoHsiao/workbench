"""本地 CI：编译 → 文档链接 → FR 追溯 → 测试 → 覆盖率 → 自检 → NFR 基准 → 品牌守卫 → 可复现构建。

发行包冒烟在 build_release 之后单独执行：python scripts/package_smoke.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, command: list[str]) -> bool:
    print(f"\n=== {name} ===", flush=True)
    completed = subprocess.run(command, cwd=REPO_ROOT)
    ok = completed.returncode == 0
    print(f"=== {name}: {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


def main() -> int:
    steps = [
        ("compile", [sys.executable, "-m", "compileall", "-q", "packages", "workbench.py"]),
        ("doc-links", [sys.executable, "scripts/check_doc_links.py"]),
        ("fr-mapping", [sys.executable, "scripts/check_fr_mapping.py"]),
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("coverage", [sys.executable, "scripts/coverage_check.py", "--min", "80", "--branches", "--min-branches", "50"]),
        ("doctor", [sys.executable, "workbench.py", "doctor"]),
        ("bench", [sys.executable, "scripts/bench.py", "--enforce", "--max-cold-start", "1.0"]),
        ("brand-guard", [sys.executable, "workbench.py", "brand-guard"]),
        ("repro", [sys.executable, "scripts/repro_check.py"]),
    ]
    results = [(name, run_step(name, command)) for name, command in steps]
    failed = [name for name, ok in results if not ok]
    print("\nCI 汇总:")
    for name, ok in results:
        print(f"- {name}: {'PASS' if ok else 'FAIL'}")
    if failed:
        print(f"\nCI 失败: {', '.join(failed)}")
        return 1
    print("\nCI 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
