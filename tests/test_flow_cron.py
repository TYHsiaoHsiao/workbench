"""五段式 cron 表达式解析与匹配（M28）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from flow import FlowError, cron_matches, next_run, parse_cron  # noqa: E402


class CronTest(unittest.TestCase):
    def test_wildcard(self) -> None:
        spec = parse_cron("* * * * *")
        self.assertEqual(tuple(len(item) for item in spec), (60, 24, 31, 12, 7))

    def test_step(self) -> None:
        spec = parse_cron("*/15 */6 * * *")
        self.assertEqual(spec[0], frozenset(range(0, 60, 15)))
        self.assertEqual(spec[1], frozenset({0, 6, 12, 18}))

    def test_range_and_list(self) -> None:
        spec = parse_cron("1-5,10 9-11 * * *")
        self.assertEqual(spec[0], frozenset({1, 2, 3, 4, 5, 10}))
        self.assertEqual(spec[1], frozenset({9, 10, 11}))

    def test_invalid_expressions(self) -> None:
        for expression in (
            "* * *",
            "* * * * * *",
            "60 * * * *",
            "*/0 * * * *",
            "*/x * * * *",
            "1-2-3 * * * *",
            "",
        ):
            with self.assertRaises(FlowError):
                parse_cron(expression)

    def test_cron_matches_weekday_mapping(self) -> None:
        monday = datetime(2026, 11, 16, 10, 30)  # 2026-11-16 为周一
        self.assertTrue(cron_matches(parse_cron("30 10 * * 1"), monday))
        self.assertFalse(cron_matches(parse_cron("30 10 * * 0"), monday))
        self.assertTrue(cron_matches(parse_cron("30 10 * * 0"), datetime(2026, 11, 15, 10, 30)))

    def test_cron_matches_day_or_weekday(self) -> None:
        spec = parse_cron("0 0 16 * 0")  # 每月 16 号或每周日
        self.assertTrue(cron_matches(spec, datetime(2026, 11, 16, 0, 0)))
        self.assertTrue(cron_matches(spec, datetime(2026, 11, 15, 0, 0)))
        self.assertFalse(cron_matches(spec, datetime(2026, 11, 17, 0, 0)))

    def test_cron_matches_fields(self) -> None:
        spec = parse_cron("5 3 1 1 *")
        self.assertTrue(cron_matches(spec, datetime(2026, 1, 1, 3, 5)))
        self.assertFalse(cron_matches(spec, datetime(2026, 1, 1, 3, 6)))
        self.assertFalse(cron_matches(spec, datetime(2026, 1, 2, 3, 5)))

    def test_next_run(self) -> None:
        spec = parse_cron("*/5 * * * *")
        self.assertEqual(next_run(spec, datetime(2026, 11, 16, 10, 2, 30)), datetime(2026, 11, 16, 10, 5))
        self.assertEqual(next_run(spec, datetime(2026, 11, 16, 10, 5)), datetime(2026, 11, 16, 10, 10))


if __name__ == "__main__":
    unittest.main()
