"""覆盖率检查（M20 行覆盖 + M25 分支覆盖，零第三方依赖）。

用标准库测量 ``packages/`` 的行覆盖率与分支覆盖率：
- Python 3.12+ 使用 ``sys.monitoring``（开销低，推荐）；
- 旧版本行覆盖回退到 ``trace`` 模块；**分支覆盖需要 Python 3.12+ 的 BRANCH 事件**。

用法::

    python scripts/coverage_check.py                       # 行覆盖，默认门槛 70%
    python scripts/coverage_check.py --min 80              # PRD NFR 目标
    python scripts/coverage_check.py --branches --min-branches 70
    python scripts/coverage_check.py --json --out report.json
    python scripts/coverage_check.py --no-enforce          # 仅报告

覆盖口径：只统计仓库内 ``packages/**/*.py`` 的“可执行行”（AST 语句行）；
分支口径：对 ``dis`` 中的条件跳转（if/while/for/短路 and/or 等）统计
“跳转/不跳转”两个方向是否都到达；测试与脚本不计入分母。
``workbench.py`` 是仅 6 行的入口，不计入统计。
"""
from __future__ import annotations

import argparse
import ast
import dis
import io
import json
import sys
import traceback
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("packages",)
DEFAULT_MIN = 70.0
DEFAULT_MIN_BRANCHES = 50.0

# 条件跳转指令（3.11/3.12 名称兼容）
BRANCH_OPNAMES = frozenset(
    {
        "POP_JUMP_FORWARD_IF_FALSE",
        "POP_JUMP_FORWARD_IF_TRUE",
        "POP_JUMP_BACKWARD_IF_FALSE",
        "POP_JUMP_BACKWARD_IF_TRUE",
        "POP_JUMP_IF_FALSE",
        "POP_JUMP_IF_TRUE",
        "JUMP_IF_FALSE_OR_POP",
        "JUMP_IF_TRUE_OR_POP",
        "FOR_ITER",
    }
)


def _display_name(name: str) -> str:
    """把内部绝对路径转成相对仓库路径（外部临时路径回退为绝对路径）。"""
    path = Path(name)
    if not path.is_absolute():
        return name
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


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
            files[str(base.resolve())] = executable_lines(base)
        elif base.is_dir():
            for path in sorted(base.rglob("*.py")):
                rel = path.relative_to(root).as_posix()
                if "__pycache__" in rel:
                    continue
                files[str(path.resolve())] = executable_lines(path)
    return {name: lines for name, lines in files.items() if lines}


# ---------------------------------------------------------------------------
# 分支点静态收集
# ---------------------------------------------------------------------------


def _code_objects(code: types.CodeType):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _code_objects(const)


def _match_key(code: types.CodeType) -> tuple[str, int, int]:
    """代码对象匹配键：函数名 + 首行 + 字节码长度（跨编译实例稳定）。"""
    return (code.co_name, code.co_firstlineno, len(code.co_code))


def branch_points(path: Path) -> dict[tuple[str, int, int], dict[int, dict[str, int]]]:
    """静态收集文件中的分支点。

    返回 ``{(co_name, co_firstlineno, len(co_code)): {offset: {"line", "target", "fall"}}}``。
    """
    try:
        source = path.read_bytes()
        module = compile(source, str(path.resolve()), "exec")
    except (SyntaxError, OSError, ValueError):
        return {}
    points: dict[tuple[str, int, int], dict[int, dict[str, int]]] = {}
    for code in _code_objects(module):
        instructions = list(dis.get_instructions(code))
        last_line = code.co_firstlineno
        current: dict[int, dict[str, int]] = {}
        for index, ins in enumerate(instructions):
            positions = getattr(ins, "positions", None)
            lineno = getattr(positions, "lineno", None) if positions is not None else None
            if lineno:
                last_line = lineno
            if ins.opname not in BRANCH_OPNAMES:
                continue
            target = ins.argval if isinstance(ins.argval, int) else None
            if target is None or index + 1 >= len(instructions):
                continue
            fall = instructions[index + 1].offset
            current[ins.offset] = {"line": last_line, "target": target, "fall": fall}
        if current:
            points[_match_key(code)] = current
    return points


def collect_branch_targets(root: Path = REPO_ROOT) -> dict[str, dict[tuple[str, int, int], dict[int, dict[str, int]]]]:
    result: dict[str, dict[tuple[str, int, int], dict[int, dict[str, int]]]] = {}
    for name in collect_targets(root):
        points = branch_points(Path(name))
        if points:
            result[name] = points
    return result


def _collect_code_from_object(obj: object, found: list[types.CodeType]) -> None:
    """递归收集函数/类/属性里的 code 对象（含嵌套函数与 lambda 的 code consts）。"""
    if isinstance(obj, types.FunctionType):
        found.extend(_code_objects(obj.__code__))
        return
    if isinstance(obj, (staticmethod, classmethod)):
        _collect_code_from_object(obj.__func__, found)
        return
    if isinstance(obj, property):
        for accessor in (obj.fget, obj.fset, obj.fdel):
            if accessor is not None:
                _collect_code_from_object(accessor, found)
        return
    if isinstance(obj, type):
        for member in vars(obj).values():
            _collect_code_from_object(member, found)


def import_target_code(
    root: Path = REPO_ROOT,
) -> dict[str, dict[tuple[str, int, int], types.CodeType]]:
    """在测试前导入 ``packages`` 下全部模块，登记可局部监控的 code 对象。

    只对可导入模块登记局部 BRANCH 事件，避免全解释器分支事件带来的巨大开销；
    分母统计也相应只保留被登记代码对象的分支点（模块顶层代码不在分母内）。
    """
    import importlib
    import pkgutil

    packages_dir = root / "packages"
    for extra in (str(root), str(packages_dir)):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    registry: dict[str, dict[tuple[str, int, int], types.CodeType]] = {}
    for info in pkgutil.walk_packages([str(packages_dir)]):
        try:
            module = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 - 导入失败则跳过该模块
            continue
        found: list[types.CodeType] = []
        for value in vars(module).values():
            _collect_code_from_object(value, found)
        for code in found:
            try:
                filename = str(Path(code.co_filename).resolve())
            except (OSError, RuntimeError):
                continue
            registry.setdefault(filename, {}).setdefault(_match_key(code), code)
    return registry



def mark_branch_outcome(
    static: dict[tuple[str, int, int], dict[int, dict[str, int]]],
    covered: set[tuple[tuple[str, int, int], int, str]],
    code: types.CodeType,
    offset: int,
    destination: int,
) -> None:
    """记录一次分支跳转结果（供测试与运行时回调复用）。"""
    points = static.get(_match_key(code))
    if not points:
        return
    point = points.get(offset)
    if not point:
        return
    key = _match_key(code)
    if destination == point["target"]:
        covered.add((key, offset, "taken"))
    elif destination == point["fall"]:
        covered.add((key, offset, "fall"))


def summarize_branches(
    static: dict[str, dict[tuple[str, int, int], dict[int, dict[str, int]]]],
    covered: dict[str, set[tuple[tuple[str, int, int], int, str]]],
) -> dict[str, object]:
    """汇总分支覆盖率。"""
    total = covered_count = 0
    rows: list[dict[str, object]] = []
    for name, points in static.items():
        file_total = 0
        file_covered = 0
        hit = covered.get(name, set())
        for key, offsets in points.items():
            for offset in offsets:
                for side in ("taken", "fall"):
                    file_total += 1
                    if (key, offset, side) in hit:
                        file_covered += 1
        total += file_total
        covered_count += file_covered
        rows.append(
            {
                "file": _display_name(name),
                "total": file_total,
                "covered": file_covered,
                "percent": round(file_covered * 100.0 / file_total, 1) if file_total else 0.0,
            }
        )
    rows.sort(key=lambda row: row["percent"])
    percent = round(covered_count * 100.0 / total, 2) if total else 0.0
    return {"total": total, "covered": covered_count, "percent": percent, "files": rows}


# ---------------------------------------------------------------------------
# 运行时测量
# ---------------------------------------------------------------------------


def _run_unittest() -> None:
    import unittest

    for extra in (str(REPO_ROOT), str(REPO_ROOT / "packages")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    loader = unittest.TestLoader()
    suite = loader.discover(str(REPO_ROOT / "tests"))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    result = runner.run(suite)
    if not result.wasSuccessful():
        if stream.getvalue():
            sys.stderr.write(stream.getvalue())
        names = [test.id() for test, _ in result.failures + result.errors]
        detail = f"：{', '.join(names)}" if names else ""
        raise RuntimeError(
            "测试未通过（覆盖率统计前必须先让全部测试通过）："
            f"failures={len(result.failures)} errors={len(result.errors)}{detail}"
        )


def _runtime_measure(
    line_covered: dict[str, set[int]] | None,
    branch_static: dict[str, dict[tuple[str, int, int], dict[int, dict[str, int]]]] | None,
) -> tuple[
    dict[str, set[tuple[tuple[str, int, int], int, str]]],
    dict[str, dict[tuple[str, int, int], dict[int, dict[str, int]]]],
]:
    """运行全部测试，收集行覆盖与局部分支结果（仅 Python 3.12+ 支持分支）。"""
    covered_branches: dict[str, set[tuple[tuple[str, int, int], int, str]]] = {
        name: set() for name in (branch_static or {})
    }
    if hasattr(sys, "monitoring"):
        mon = sys.monitoring
        tool = mon.PROFILER_ID
        mon.use_tool_id(tool, "workbench-coverage")
        code_index: dict[types.CodeType, tuple[tuple[str, int, int], set, dict]] = {}

        def on_line(code, line):  # noqa: ANN001
            filename = code.co_filename
            if line_covered is not None and filename in line_covered:
                line_covered[filename].add(line)

        mon.register_callback(tool, mon.events.LINE, on_line)
        mon.set_events(tool, mon.events.LINE)
        try:
            if branch_static is not None:
                # 先全局开 LINE，再导入目标模块：导入期的行也算覆盖。
                registry = import_target_code()
                static_active: dict[str, dict[tuple[str, int, int], dict[int, dict[str, int]]]] = {}
                for name, points in branch_static.items():
                    registered = registry.get(name)
                    if not registered:
                        continue
                    active = {key: offsets for key, offsets in points.items() if key in registered}
                    if not active:
                        continue
                    static_active[name] = active
                    covered = covered_branches.setdefault(name, set())
                    for key, code in registered.items():
                        points_for_code = active.get(key)
                        if points_for_code:
                            code_index[code] = (key, covered, points_for_code)

                def on_branch(code, offset, destination):  # noqa: ANN001
                    entry = code_index.get(code)
                    if entry is None:
                        return
                    key, covered, points = entry
                    point = points.get(offset)
                    if point is None:
                        return
                    if destination == point["target"]:
                        covered.add((key, offset, "taken"))
                    elif destination == point["fall"]:
                        covered.add((key, offset, "fall"))

                mon.register_callback(tool, mon.events.BRANCH, on_branch)
                for code in code_index:
                    mon.set_local_events(tool, code, mon.events.BRANCH)
                branch_static = static_active
            _run_unittest()
        finally:
            mon.set_events(tool, 0)
            mon.register_callback(tool, mon.events.LINE, None)
            if branch_static is not None:
                mon.register_callback(tool, mon.events.BRANCH, None)
                for code in list(code_index):
                    try:
                        mon.set_local_events(tool, code, 0)
                    except ValueError:
                        pass
            mon.free_tool_id(tool)
    else:  # pragma: no cover - 3.11 及以下兜底
        if branch_static is not None:
            raise RuntimeError("分支覆盖率需要 Python 3.12+（sys.monitoring BRANCH 事件）")
        import trace

        # count=1/trace=0：只收集行命中，不打印逐行轨迹（trace=1 会打印每一行，CI 日志巨大且可能编码报错）。
        tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix])
        tracer.runfunc(_run_unittest)
        counts = tracer.results().counts
        for (filename, lineno), _count in counts.items():
            resolved = str(Path(filename).resolve())
            if line_covered is not None and resolved in line_covered:
                line_covered[resolved].add(lineno)
    return covered_branches, branch_static or {}


def measure(
    root: Path = REPO_ROOT, *, branches: bool = False
) -> tuple[dict[str, dict[str, int]], dict[str, object] | None]:
    """运行全部测试并统计行覆盖（及可选分支覆盖）。

    返回 ``(行覆盖报告, 分支摘要或 None)``。
    """
    targets = collect_targets(root)
    line_covered: dict[str, set[int]] = {name: set() for name in targets}
    branch_static = collect_branch_targets(root) if branches else None
    branch_covered, branch_static = _runtime_measure(line_covered, branch_static)

    report: dict[str, dict[str, int]] = {}
    for name, lines in targets.items():
        hit = line_covered.get(name, set())
        report[name] = {
            "total": len(lines),
            "covered": len(lines & hit),
            "missing": len(lines - hit),
        }
    branch_summary = summarize_branches(branch_static, branch_covered) if branch_static else None
    return report, branch_summary


def summarize(report: dict[str, dict[str, int]]) -> dict[str, object]:
    total = sum(item["total"] for item in report.values())
    covered = sum(item["covered"] for item in report.values())
    percent = round(covered * 100.0 / total, 2) if total else 0.0
    files = sorted(
        (
            {
                "file": _display_name(name),
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
    parser = argparse.ArgumentParser(description="覆盖率检查（行 + 分支，标准库实现）")
    parser.add_argument("--min", type=float, default=DEFAULT_MIN, help="行覆盖率门槛（百分比）")
    parser.add_argument("--branches", action="store_true", help="同时统计分支覆盖率（需要 Python 3.12+）")
    parser.add_argument(
        "--min-branches",
        type=float,
        default=DEFAULT_MIN_BRANCHES,
        help="分支覆盖率门槛（百分比，仅 --branches 时生效）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（配合 --out 写文件，避免被测试子进程输出污染）")
    parser.add_argument("--out", default="", help="JSON 报告输出路径")
    parser.add_argument("--no-enforce", action="store_true", help="只报告，不因低于门槛失败")
    args = parser.parse_args(argv)

    try:
        report, branch_summary = measure(branches=args.branches)
        summary = summarize(report)
        if branch_summary is not None:
            summary["branch"] = branch_summary
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
        if branch_summary is not None:
            print(f"分支覆盖率: {branch_summary['percent']}%（{branch_summary['covered']}/{branch_summary['total']} 条分支）")
            for row in branch_summary["files"][:5]:
                print(f"  分支最低: {row['file']} {row['percent']}%")
    failed = False
    if not args.no_enforce and summary["percent"] < args.min:
        print(f"行覆盖率 {summary['percent']}% 低于门槛 {args.min}%", file=sys.stderr)
        failed = True
    if (
        branch_summary is not None
        and not args.no_enforce
        and branch_summary["percent"] < args.min_branches
    ):
        print(
            f"分支覆盖率 {branch_summary['percent']}% 低于门槛 {args.min_branches}%",
            file=sys.stderr,
        )
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
