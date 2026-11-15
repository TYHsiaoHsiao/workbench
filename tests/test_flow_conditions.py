"""条件表达式求值（M7）：flow.conditions。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from flow import ConditionError, evaluate  # noqa: E402


class ConditionsTest(unittest.TestCase):
    def test_always_never_and_default(self) -> None:
        self.assertTrue(evaluate("always", {}))
        self.assertFalse(evaluate("never", {}))
        self.assertTrue(evaluate("", {}))

    def test_stage_comparison(self) -> None:
        state = {"stage": "04", "version": "v03"}
        self.assertTrue(evaluate("state.stage >= 03", state))
        self.assertFalse(evaluate("state.stage <= 03", state))
        self.assertTrue(evaluate("state.stage != done", state))
        self.assertTrue(evaluate("state.stage == 04", state))

    def test_version_comparison(self) -> None:
        state = {"version": "v05"}
        self.assertTrue(evaluate("state.version >= v05", state))
        self.assertTrue(evaluate("state.version <= v05", state))
        self.assertTrue(evaluate("state.version != v04", state))

    def test_iteration_comparison(self) -> None:
        self.assertTrue(evaluate("iteration >= 2", {}, iteration=2))
        self.assertFalse(evaluate("iteration >= 3", {}, iteration=2))
        self.assertTrue(evaluate("iteration == 3", {}, iteration=3))
        self.assertTrue(evaluate("iteration <= 3", {}, iteration=2))

    def test_invalid_expression_raises(self) -> None:
        with self.assertRaises(ConditionError):
            evaluate("state.stage like 03", {"stage": "03"})
        with self.assertRaises(ConditionError):
            evaluate("1 + 1", {})
        with self.assertRaises(ConditionError):
            evaluate("state.stage >= 09", {"stage": "03"})


if __name__ == "__main__":
    unittest.main()
