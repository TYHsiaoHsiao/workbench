"""阶段注册表测试：结构、引用完整性与查询接口。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.registry import (  # noqa: E402
    DEFAULT_REGISTRY,
    RegistryError,
    load_registry,
    validate_registry,
)


class StageRegistryTest(unittest.TestCase):
    def test_registry_is_valid(self) -> None:
        self.assertEqual([], validate_registry())

    def test_eight_stages_and_order(self) -> None:
        registry = load_registry()
        self.assertEqual([f"{i:02d}" for i in range(1, 9)], registry.ids())
        self.assertEqual("03", registry.stage("3")["id"])
        self.assertTrue(registry.stage("03")["optional"])

    def test_knowledge_bridge_is_not_a_stage(self) -> None:
        registry = load_registry()
        bridge = registry.knowledge_bridge
        self.assertEqual("film-knowledge-bridge", bridge["skill"])
        self.assertFalse(bridge["is_stage"])
        self.assertEqual("off", bridge["default"])
        self.assertNotIn(bridge["skill"], registry.ids())

    def test_next_stage(self) -> None:
        registry = load_registry()
        self.assertEqual("02", registry.next_stage_id("01"))
        self.assertEqual("05", registry.next_stage_id("04"))
        self.assertEqual("done", registry.next_stage_id("08"))

    def test_stage_08_two_step_gates(self) -> None:
        registry = load_registry()
        gate_ids = [gate["id"] for gate in registry.gates("08")]
        self.assertEqual(["shot_plan_gate", "model_choice"], gate_ids)
        self.assertEqual(["seedance_2_0", "minimax_h3", "dual"],
                         registry.stage("08")["model_options"])

    def test_stage_06_style_mount(self) -> None:
        registry = load_registry()
        self.assertTrue(registry.stage("06")["style_mount"]["enabled"])
        self.assertFalse(registry.stage("05")["style_mount"]["enabled"])

    def test_unknown_stage_raises(self) -> None:
        registry = load_registry()
        with self.assertRaises(KeyError):
            registry.stage("09")

    def test_broken_registry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
            data["stages"][0]["downstream"] = ["99"]
            path = Path(tmp) / "broken.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            errors = validate_registry(path)
            self.assertTrue(any("未知阶段" in error for error in errors))
            with self.assertRaises(RegistryError):
                load_registry(path)

    def test_duplicate_stage_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
            data["stages"][1]["id"] = data["stages"][0]["id"]
            path = Path(tmp) / "duplicate.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(any("重复" in error for error in validate_registry(path)))


if __name__ == "__main__":
    unittest.main()
