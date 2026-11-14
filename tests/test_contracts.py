"""契约层测试：schema 可加载、正反例校验。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from contracts import list_schemas, load_schema, validate, validate_file  # noqa: E402
from core_router.state import default_state  # noqa: E402


class ContractsTest(unittest.TestCase):
    def test_schemas_are_loadable(self) -> None:
        names = list_schemas()
        self.assertGreaterEqual(len(names), 6)
        for name in names:
            schema = load_schema(name)
            self.assertIn("title", schema)

    def test_default_state_is_valid(self) -> None:
        state = default_state("示例项目")
        self.assertEqual([], validate(state, schema_name="state.schema.json"))

    def test_missing_required_field_is_reported(self) -> None:
        state = default_state("示例项目")
        del state["entry"]
        errors = validate(state, schema_name="state.schema.json")
        self.assertTrue(errors)
        self.assertIn("$.entry", errors[0])

    def test_bad_enum_is_reported(self) -> None:
        state = default_state("示例项目")
        state["mode"] = "invalid-mode"
        errors = validate(state, schema_name="state.schema.json")
        self.assertTrue(any("$.mode" in error for error in errors))

    def test_bad_pattern_is_reported(self) -> None:
        state = default_state("示例项目")
        state["version"] = "1"
        errors = validate(state, schema_name="state.schema.json")
        self.assertTrue(any("$.version" in error for error in errors))

    def test_additional_property_is_reported(self) -> None:
        state = default_state("示例项目")
        state["unknown_field"] = True
        errors = validate(state, schema_name="state.schema.json")
        self.assertTrue(any("unknown_field" in error for error in errors))

    def test_const_violation_is_reported(self) -> None:
        state = default_state("示例项目")
        state["contract_version"] = "2.0"
        errors = validate(state, schema_name="state.schema.json")
        self.assertTrue(any("contract_version" in error for error in errors))

    def test_validate_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps(default_state("文件项目"), ensure_ascii=False),
                            encoding="utf-8")
            self.assertEqual([], validate_file(path, "state.schema.json"))
            data = default_state("文件项目")
            data["stage"] = "09"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(validate_file(path, "state.schema.json"))


if __name__ == "__main__":
    unittest.main()
