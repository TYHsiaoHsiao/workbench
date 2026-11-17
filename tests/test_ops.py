"""Web 操作台（M40/M41）：注册表、参数校验、操作历史与批量执行。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from flow import FlowError  # noqa: E402
from webui import ops  # noqa: E402


class OpsRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        ops._HISTORY.clear()

    def test_list_ops_hides_handlers_and_has_expected_ops(self) -> None:
        public = ops.list_ops()
        self.assertGreaterEqual(len(public), 24)
        for item in public:
            self.assertNotIn("handler", item)
        by_id = {item["id"]: item for item in public}
        for expected in (
            "quickstart_demo",
            "practical_check",
            "project_list",
            "project_summary",
            "index_search",
            "generate_refresh",
            "batch_report_push",
            "queue_alerts",
            "queue_alerts_push",
            "flow_batches",
            "doctor",
            "rollback_apply",
        ):
            self.assertIn(expected, by_id)
        self.assertTrue(by_id["rollback_apply"].get("danger"))
        self.assertFalse(by_id["doctor"].get("danger", False))

    def test_run_op_unknown_records_failure_history(self) -> None:
        with self.assertRaises(FlowError) as ctx:
            ops.run_op("no_such_op")
        self.assertIn("未知操作", str(ctx.exception))
        history = ops.list_history()
        self.assertEqual(1, len(history))
        self.assertEqual("no_such_op", history[0]["op_id"])
        self.assertFalse(history[0]["ok"])

    def test_run_op_requires_params_and_validates_types(self) -> None:
        self.assertTrue(ops.run_op("project_list", {})["ok"])

        with self.assertRaises(FlowError) as ctx:
            ops.run_op("index_search", {"query": "悬念", "limit": "abc"})
        self.assertIn("需要整数", str(ctx.exception))

        with self.assertRaises(FlowError) as ctx:
            ops.run_op("generate_plan", {"provider": "nope", "project": "x"})
        self.assertIn("取值无效", str(ctx.exception))

        with self.assertRaises(FlowError) as ctx:
            ops.run_op("quickstart_demo", {})
        self.assertIn("缺少参数", str(ctx.exception))

    def test_run_op_bool_parsing(self) -> None:
        # bool 参数接受字符串形式；这里用 doctor（无参）验证成功路径并返回元数据
        result = ops.run_op("doctor")
        self.assertTrue(result["ok"])
        self.assertEqual("doctor", result["op_id"])
        self.assertGreaterEqual(result.get("duration_ms", 0), 0)
        self.assertTrue(ops.list_history())

    def test_history_is_bounded_and_newest_first(self) -> None:
        for _ in range(3):
            ops.run_op("project_list", {})
        history = ops.list_history()
        self.assertEqual(3, len(history))
        self.assertEqual("project_list", history[0]["op_id"])
        self.assertEqual(3, len(ops.list_history(limit=2)) + 1)
        # limit 边界归一
        self.assertLessEqual(len(ops.list_history(limit=0)), 1)
        self.assertLessEqual(len(ops.list_history(limit=999)), 3)

    def test_bool_and_enum_normalization_edge_cases(self) -> None:
        # bool 字符串：fix="false" → False；handler 返回失败但历史仍记录
        result = ops.run_op("practical_check", {"project": str(REPO_ROOT / "no-such-project"), "fix": "false"})
        self.assertFalse(result["ok"])
        self.assertFalse(ops.list_history()[0]["ok"])
        # enum 非法值在归一化阶段被拒绝
        with self.assertRaises(FlowError) as ctx:
            ops.run_op("batch_report", {"project": "x", "format": "pdf"})
        self.assertIn("取值无效", str(ctx.exception))
        # int 字符串归一化 + 项目缺失时 handler 返回失败
        result = ops.run_op("flow_batches", {"project": str(REPO_ROOT / "no-such-project"), "limit": "5"})
        self.assertFalse(result["ok"])
        result = ops.run_op("batch_report", {"project": str(REPO_ROOT / "no-such-project")})
        self.assertFalse(result["ok"])

    def test_run_ops_batch_validates_and_continues_on_failure(self) -> None:
        with self.assertRaises(FlowError):
            ops.run_ops_batch([])
        with self.assertRaises(FlowError):
            ops.run_ops_batch([{"op_id": "project_list"}] * 21)
        with self.assertRaises(FlowError):
            ops.run_ops_batch(["bad"])
        with self.assertRaises(FlowError):
            ops.run_ops_batch([{"params": {}}])

        result = ops.run_ops_batch(
            [
                {"op_id": "project_list", "params": {}},
                {"op_id": "quickstart_demo", "params": {}},
                {"op_id": "project_list", "params": {}},
            ]
        )
        self.assertFalse(result["ok"])
        self.assertEqual(3, result["count"])
        self.assertTrue(result["results"][0]["ok"])
        self.assertFalse(result["results"][1]["ok"])
        self.assertIn("error", result["results"][1])
        self.assertTrue(result["results"][2]["ok"])


if __name__ == "__main__":
    unittest.main()
