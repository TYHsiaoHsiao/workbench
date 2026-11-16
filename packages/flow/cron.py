"""五段式 cron 表达式解析（零依赖，分钟粒度）。

支持 ``*``、``*/n``、``a-b``、``a-b/n``、数字与逗号列表；字段顺序与范围：
分 0–59、时 0–23、日 1–31、月 1–12、周 0–6（0=周日）。
日与周同时受限时按常见 cron 语义取「或」。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .graph import FlowError

FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
FIELD_NAMES = ("分", "时", "日", "月", "周")


def _expand(token: str, low: int, high: int, name: str) -> frozenset[int]:
    values: set[int] = set()
    for raw in token.split(","):
        part = raw.strip()
        if not part:
            raise FlowError(f"cron {name}字段包含空项: {token}")
        step = 1
        if "/" in part:
            base, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) <= 0:
                raise FlowError(f"cron {name}字段步长无效: {part}")
            step = int(step_text)
            part = base
        if part == "*":
            start, end = low, high
        elif "-" in part:
            left, right = part.split("-", 1)
            if not (left.isdigit() and right.isdigit()):
                raise FlowError(f"cron {name}字段范围无效: {part}")
            start, end = int(left), int(right)
            if start > end:
                raise FlowError(f"cron {name}字段范围起点大于终点: {part}")
        elif part.isdigit():
            start = end = int(part)
        else:
            raise FlowError(f"cron {name}字段无效: {part}")
        if start < low or end > high:
            raise FlowError(f"cron {name}字段超出范围 {low}-{high}: {part}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


def parse_cron(expression: str) -> tuple[frozenset[int], ...]:
    """把五段式 cron 解析为五个取值集合；非法表达式抛 FlowError。"""
    if not isinstance(expression, str):
        raise FlowError("cron 表达式必须是字符串")
    parts = expression.split()
    if len(parts) != 5:
        raise FlowError("cron 表达式需要 5 段（分 时 日 月 周），如 */5 * * * *")
    return tuple(
        _expand(part, low, high, name)
        for part, (low, high), name in zip(parts, FIELD_RANGES, FIELD_NAMES)
    )


def cron_matches(spec: tuple[frozenset[int], ...], moment: datetime) -> bool:
    """判断时刻是否命中 cron（秒不参与匹配）。"""
    minute, hour, day, month, weekday = spec
    if moment.minute not in minute or moment.hour not in hour or moment.month not in month:
        return False
    day_ok = moment.day in day
    weekday_ok = ((moment.weekday() + 1) % 7) in weekday  # Python 周一=0 → cron 周一=1
    restricted_day = day != frozenset(range(1, 32))
    restricted_weekday = weekday != frozenset(range(0, 7))
    if restricted_day and restricted_weekday:
        return day_ok or weekday_ok
    return day_ok and weekday_ok


def next_run(spec: tuple[frozenset[int], ...], after: datetime | None = None) -> datetime:
    """返回 after 之后（不含当分钟）最近一次命中的分钟。"""
    moment = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if cron_matches(spec, moment):
            return moment
        moment += timedelta(minutes=1)
    raise FlowError("cron 表达式在一年内没有匹配时间")


__all__ = ["FIELD_NAMES", "FIELD_RANGES", "cron_matches", "next_run", "parse_cron"]
