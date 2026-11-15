"""行覆盖率检查（M20，零第三方依赖）。

用标准库测量 ``packages/`` 与 ``workbench.py`` 的行覆盖率：
- Python 3.12+ 使用 ``sys.monitoring``（开销低，推荐）；
- 旧版本回退到 ``trace`` 模块（较慢，仅作兜底）。

用法::

    python scripts/coverage_check.py                 # 默认门槛 70%
    python scripts/coverage_check.py --min 80        # PRD NFR 目标
    python scripts/coverage_check.py --json
    python scripts/coverage_check.py --no-enforce    # 仅报告

覆盖口径：只统计仓库内 ``packages/**/*.py`` 的“可执行行”（AST 语句行），
测试与脚本不计入分母；``workbench.py`` 是仅 6 行的入口，由 subprocess E2E 覆盖，
不计入统计（否则会以 0% 稀释整体数字）。
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("packages",)
DEFAULT_MIN = 70.0


def _is_target(path: str, root: Path) -> bool:
    try:
        rel = Path(path).resolve().relative_to(root)
    except (ValueError, OSError):
        return False
    parts = rel.parts
    if parts and parts[0] == "packages":
        return True
    return rel == Path("workbench.py")


def executable_lines(path: Path) -> set[int]:
    """返回文件的可执行行号集合（AST 语句的起始行）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return set()
    lines: set[int] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.stmt) and not isinstance(node, ast.ImportFrom):
            is_docstring = (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            if not is_docstring:
                lines.add(getattr(node, "lineno", 0))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    lines.discard(0)
    return lines


def collect_targets(root: Path = REPO_ROOT) -> dict[str, set[int]]:
    files: dict[str, set[int]] = {}
    for name in TARGETS:
        base = root / name
        if base.is_file():
            files[str(base)] = executable_lines(base)
        elif base.is_dir():
            for path in sorted(base.rglob("*.py")):
                rel = path.relative_to(root).as_posix()
                if "__pycache__" in rel:
                    continue
                files[str(path.resolve())] = executable_lines(path)
    return {name: lines for name, lines in files.items() if lines}


def _run_unittest() -> None:
    import unittest

    for extra in (str(REPO_ROOT), str(REPO_ROOT / "packages")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    loader = unittest.TestLoader()
    suite = loader.discover(str(REPO_ROOT / "tests"))
    runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise RuntimeError(
            "测试未通过（覆盖率统计前必须先让全部测试通过）："
            f"failures={len(result.failures)} errors={len(result.errors)}"
        )


def measure(root: Path = REPO_ROOT) -> dict[str, dict[str, int]]:
    """运行全部测试并统计行覆盖率，返回 {文件: {total, covered, missing}}。"""
    targets = collect_targets(root)
    covered: dict[str, set[int]] = {name: set() for name in targets}

    if hasattr(sys, "monitoring"):
        mon = sys.monitoring
        tool = mon.PROFILER_ID
        mon.use_tool_id(tool, "workbench-coverage")

        def on_line(code, line):  # noqa: ANN001
            filename = code.co_filename
            if filename in covered:
                covered[filename].add(line)

        mon.register_callback(tool, mon.events.LINE, on_line)
        mon.set_events(tool, mon.events.LINE)
        try:
            _run_unittest()
        finally:
            mon.set_events(tool, 0)
            mon.register_callback(tool, mon.events.LINE, None)
            mon.free_tool_id(tool)
    else:  # pragma: no cover - 3.11 及以下兜底
        import trace

        tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix])
        tracer.runfunc(_run_unittest)
        counts = tracer.results().counts
        for (filename, lineno), _count in counts.items():
            resolved = str(Path(filename).resolve())
            if resolved in covered:
                covered[resolved].add(lineno)

    report: dict[str, dict[str, int]] = {}
    for name, lines in targets.items():
        hit = covered.get(name, set())
        report[name] = {
            "total": len(lines),
            "covered": len(lines & hit),
            "missing": len(lines - hit),
        }
    return report


def summarize(report: dict[str, dict[str, int]]) -> dict[str, object]:
    total = sum(item["total"] for item in report.values())
    covered = sum(item["covered"] for item in report.values())
    percent = round(covered * 100.0 / total, 2) if total else 0.0
    files = sorted(
        (
            {
                "file": Path(name).relative_to(REPO_ROOT).as_posix()
                if Path(name).is_absolute()
                else name,
                "total": item["total"],
                "covered": item["covered"],
                "percent": round(item["covered"] * 100.0 / item["total"], 1)
                if item["total"]
                else 0.0,
            }
            for name, item in report.items()
        ),
        key=lambda row: row["percent"],
    )
    return {"total": total, "covered": covered, "percent": percent, "files": files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="行覆盖率检查（标准库实现）")
    parser.add_argument("--min", type=float, default=DEFAULT_MIN, help="覆盖率门槛（百分比）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（配合 --out 写文件，避免被测试子进程输出污染）")
    parser.add_argument("--out", default="", help="JSON 报告输出路径")
    parser.add_argument("--no-enforce", action="store_true", help="只报告，不因低于门槛失败")
    args = parser.parse_args(argv)

    try:
        summary = summarize(measure())
    except Exception as exc:  # noqa: BLE001
        print(f"覆盖率统计失败: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    if args.json:
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
            print(f"覆盖率报告已写入: {args.out}")
        else:
            print(text)
    else:
        print(f"行覆盖率: {summary['percent']}%（{summary['covered']}/{summary['total']} 行）")
        for row in summary["files"][:5]:
            print(f"  最低: {row['file']} {row['percent']}%")
    if not args.no_enforce and summary["percent"] < args.min:
        print(f"覆盖率 {summary['percent']}% 低于门槛 {args.min}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
