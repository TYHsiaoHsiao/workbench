"""本地 CI：编译检查 -> 单元测试 -> 自检 -> 品牌守卫。"""
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
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("doctor", [sys.executable, "workbench.py", "doctor"]),
        ("brand-guard", [sys.executable, "workbench.py", "brand-guard"]),
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
