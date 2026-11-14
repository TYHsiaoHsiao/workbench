"""门禁引擎测试：阶段门禁、条件门禁、推进拦截与状态回写。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.gates import (  # noqa: E402
    DONE,
    GateError,
    advance,
    can_advance,
    conditional_gate_ids,
    ensure_stage_gates,
    fail_gate,
    gate_detail,
    mark_downstream_stale,
    pass_gate,
    pending_gates,
    waive_gate,
)
from core_router.project import create_project, load_state  # noqa: E402
from core_router.registry import load_registry  # noqa: E402
from core_router.state import validate_state  # noqa: E402


class GateEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = load_registry()
        create_project("门禁测试", base=self.tmp.name, entry="A")
        self.root = Path(self.tmp.name) / "门禁测试"
        self.state = load_state(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _pass_all(self, state: dict) -> None:
        ensure_stage_gates(state, state["stage"], self.registry)
        for item in gate_detail(state, state["stage"], self.registry):
            if item["status"] != "passed":
                pass_gate(state, item["id"], registry=self.registry)

    def test_stage01_has_two_hard_gates(self) -> None:
        detail = gate_detail(self.state, "01", self.registry)
        self.assertEqual([item["id"] for item in detail], ["positioning_menu", "sub_option_confirm"])
        self.assertTrue(all(item["type"] == "hard" for item in detail))
        self.assertEqual(pending_gates(self.state, "01", self.registry),
                         ["positioning_menu", "sub_option_confirm"])

    def test_advance_blocked_until_gates_pass(self) -> None:
        ok, reasons = can_advance(self.state, "01", self.registry)
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 2)
        with self.assertRaises(GateError):
            advance(self.state, registry=self.registry)

        self._pass_all(self.state)
        ok, reasons = can_advance(self.state, "01", self.registry)
        self.assertTrue(ok, reasons)
        next_stage = advance(self.state, registry=self.registry)
        self.assertEqual(next_stage, "02")
        self.assertEqual(self.state["version"], "v02")
        self.assertEqual(validate_state(self.state), [])
        # 新阶段门禁已自动补齐。
        self.assertIn("upstream_confirmed", pending_gates(self.state, "02", self.registry))

    def test_hard_gate_cannot_be_waived(self) -> None:
        with self.assertRaises(GateError):
            waive_gate(self.state, "positioning_menu", registry=self.registry)

    def test_soft_gate_can_be_waived(self) -> None:
        self.state["stage"] = "06"
        ensure_stage_gates(self.state, "06", self.registry)
        pass_gate(self.state, "production_data", registry=self.registry)
        waived = waive_gate(self.state, "style_card_confirm", registry=self.registry)
        self.assertEqual(waived["status"], "waived")
        ok, reasons = can_advance(self.state, "06", self.registry)
        self.assertTrue(ok, reasons)

    def test_entry_b_adds_intake_gate(self) -> None:
        create_project("接管项目", base=self.tmp.name, entry="B")
        state = load_state(Path(self.tmp.name) / "接管项目")
        ids = [item["id"] for item in gate_detail(state, "01", self.registry)]
        self.assertIn("screenplay_intake", ids)
        self.assertEqual(conditional_gate_ids(state, "01"), ["screenplay_intake"])
        self._pass_all(state)
        self.assertEqual(advance(state, registry=self.registry), "02")

    def test_knowledge_gate_only_when_bridge_on(self) -> None:
        state = load_state(self.root)
        state["stage"] = "05"
        ensure_stage_gates(state, "05", self.registry)
        self.assertNotIn(
            "knowledge_card_confirm",
            [item["id"] for item in gate_detail(state, "05", self.registry)],
        )
        state["knowledge_bridge"] = {"status": "requested", "last_card": "", "confirmed_references": []}
        ensure_stage_gates(state, "05", self.registry)
        self.assertIn(
            "knowledge_card_confirm",
            [item["id"] for item in gate_detail(state, "05", self.registry)],
        )

    def test_fail_gate_blocks_advance(self) -> None:
        self._pass_all(self.state)
        fail_gate(self.state, "positioning_menu", note="需要重做", registry=self.registry)
        ok, reasons = can_advance(self.state, "01", self.registry)
        self.assertFalse(ok)
        self.assertIn("门禁未通过: positioning_menu(failed)", reasons)

    def test_advance_to_done(self) -> None:
        self._pass_all(self.state)
        advance(self.state, registry=self.registry)
        while self.state["stage"] != DONE:
            self._pass_all(self.state)
            advance(self.state, registry=self.registry)
        self.assertEqual(self.state["stage"], DONE)
        ok, reasons = can_advance(self.state, DONE, self.registry)
        self.assertFalse(ok)
        self.assertEqual(reasons, ["项目已完成全部阶段"])

    def test_mark_downstream_stale(self) -> None:
        self.state["stage"] = "04"
        stale = mark_downstream_stale(self.state, "04", self.registry)
        self.assertEqual(stale, ["05", "06", "07", "08"])
        self.assertEqual(self.state["stale_downstream"], ["05", "06", "07", "08"])
        # 回退上游后再标记，重复项不重复。
        again = mark_downstream_stale(self.state, "04", self.registry)
        self.assertEqual(again, ["05", "06", "07", "08"])
        self.assertEqual(len(self.state["stale_downstream"]), 4)

    def test_unknown_gate_rejected(self) -> None:
        with self.assertRaises(GateError):
            pass_gate(self.state, "not_a_gate", registry=self.registry)


if __name__ == "__main__":
    unittest.main()
