"""NFR 基准（PRD §7）：CLI 冷启动与 doctor 耗时。

用法:
    python scripts/bench.py [--runs 5] [--max-cold-start 1.0] [--enforce] [--json]
退出码: 0=达标（或未启用 --enforce），1=冷启动中位数超过阈值。
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def timed(command: list[str], cwd: Path) -> tuple[float, int, str]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=180)
    return time.perf_counter() - started, completed.returncode, completed.stdout


def summarize(samples: list[float]) -> dict:
    return {
        "runs": len(samples),
        "min_ms": round(min(samples) * 1000, 1),
        "median_ms": round(statistics.median(samples) * 1000, 1),
        "max_ms": round(max(samples) * 1000, 1),
    }


def measure(runs: int = 5) -> dict:
    cold: list[float] = []
    doctor: list[float] = []
    for _ in range(max(1, runs)):
        duration, code, _ = timed([sys.executable, "workbench.py", "version"], REPO_ROOT)
        if code != 0:
            raise SystemExit("version 命令执行失败")
        cold.append(duration)
        duration, code, _ = timed([sys.executable, "workbench.py", "doctor"], REPO_ROOT)
        if code != 0:
            raise SystemExit("doctor 命令执行失败")
        doctor.append(duration)
    return {"cold_start": summarize(cold), "doctor": summarize(doctor)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NFR 基准：CLI 冷启动与 doctor 耗时")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-cold-start", type=float, default=1.0, help="冷启动中位数阈值（秒）")
    parser.add_argument("--enforce", action="store_true", help="超过阈值时返回非零退出码")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    metrics = measure(args.runs)
    cold_median_s = metrics["cold_start"]["median_ms"] / 1000.0
    ok = cold_median_s <= args.max_cold_start
    report = {
        "ok": ok,
        "cold_start": metrics["cold_start"],
        "doctor": metrics["doctor"],
        "limits": {"max_cold_start_s": args.max_cold_start},
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"CLI 冷启动：中位数 {metrics['cold_start']['median_ms']} ms"
              f"（min {metrics['cold_start']['min_ms']} / max {metrics['cold_start']['max_ms']}，"
              f"{metrics['cold_start']['runs']} 次）")
        print(f"doctor 耗时：中位数 {metrics['doctor']['median_ms']} ms")
        print(f"NFR 冷启动阈值：{args.max_cold_start}s → {'达标' if ok else '超限'}")
    if args.enforce and not ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
