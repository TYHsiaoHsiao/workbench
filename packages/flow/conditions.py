"""条件表达式求值（M7）：条件分支与循环节点共用。

安全约束：不使用 eval/exec，只支持少量固定句式，避免流程文件注入任意代码。
支持的表达式（大小写不敏感、允许首尾空白）：
- always / never
- state.stage == 05 / state.stage != done
- state.stage >= 05 / state.stage <= 05
- iteration >= 3 / iteration <= 3 / iteration == 3
- state.version >= v05（按 vNN 数字比较）
"""
from __future__ import annotations

import re
from typing import Any

STAGE_SEQUENCE = [f"0{index}" for index in range(1, 9)] + ["done"]


class ConditionError(Exception):
    """条件表达式无法解析或求值。"""


def _stage_rank(value: str) -> int | None:
    if value in STAGE_SEQUENCE:
        return STAGE_SEQUENCE.index(value)
    return None


def _version_rank(value: str) -> int | None:
    match = re.fullmatch(r"v(\d{2,})", str(value).strip())
    if not match:
        return None
    return int(match.group(1))


def evaluate(expression: str, state: dict[str, Any], iteration: int = 0) -> bool:
    """求值条件表达式；非法表达式抛 ConditionError（由节点包装为 NodeError）。"""
    text = str(expression or "always").strip().lower()
    if text in {"", "always"}:
        return True
    if text == "never":
        return False

    match = re.fullmatch(r"state\.stage\s*(==|!=|>=|<=)\s*(\d{2}|done)", text)
    if match:
        operator, right = match.group(1), match.group(2)
        left_rank = _stage_rank(str(state.get("stage") or ""))
        right_rank = _stage_rank(right)
        if left_rank is None or right_rank is None:
            raise ConditionError(f"无法比较阶段: {expression}")
        return _compare(left_rank, right_rank, operator)

    match = re.fullmatch(r"state\.version\s*(==|!=|>=|<=)\s*(v\d{2,})", text)
    if match:
        operator, right = match.group(1), match.group(2)
        left_rank = _version_rank(str(state.get("version") or ""))
        right_rank = _version_rank(right)
        if left_rank is None or right_rank is None:
            raise ConditionError(f"无法比较版本: {expression}")
        return _compare(left_rank, right_rank, operator)

    match = re.fullmatch(r"iteration\s*(==|!=|>=|<=)\s*(\d+)", text)
    if match:
        operator, right = match.group(1), int(match.group(2))
        return _compare(int(iteration), right, operator)

    raise ConditionError(
        f"无法解析条件表达式: {expression}（支持 always/never、state.stage 比较、state.version 比较、iteration 比较）"
    )


def _compare(left: int, right: int, operator: str) -> bool:
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    raise ConditionError(f"不支持的比较运算符: {operator}")
