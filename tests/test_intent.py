"""意图路由测试：维护口令隔离、知识库触发、阶段/入口/修订识别。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.intent import IntentError, classify, load_rules, normalize, route  # noqa: E402


class IntentTest(unittest.TestCase):
    def test_rules_file_loads(self) -> None:
        rules = load_rules()
        self.assertEqual(rules["contract_version"], "1.0")
        self.assertIn("maintenance", rules)
        self.assertEqual(len(rules["stages"]), 8)

    def test_maintenance_isolated(self) -> None:
        result = classify("请配置本地知识库")
        self.assertEqual(result["kind"], "maintenance")
        self.assertTrue(result["is_maintenance"])
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["command"], "configure_knowledge")

    def test_maintenance_priority_over_knowledge_and_stage(self) -> None:
        # 同时出现知识库触发词与维护口令时，维护口令优先，绝不进入创作。
        result = classify("调用本地知识库后帮我更新知识库")
        self.assertEqual(result["kind"], "maintenance")
        self.assertEqual(result["command"], "update_knowledge")

    def test_organize_scripts_maintenance(self) -> None:
        result = classify("整理新剧本并更新知识库")
        self.assertEqual(result["kind"], "maintenance")
        self.assertEqual(result["command"], "organize_scripts")
        self.assertNotIn("stage", result)

    def test_knowledge_triggers(self) -> None:
        for text in ("调用本地知识库", "查本地剧本", "知识库B", "知识库C", "匹配本地参考", "只查方法书"):
            with self.subTest(text=text):
                result = classify(text)
                self.assertEqual(result["kind"], "knowledge", result)
                self.assertEqual(result["command"], "knowledge_retrieve")

    def test_direct_entries(self) -> None:
        self.assertEqual(classify("只做CINEDANCE")["stage"], "08")
        self.assertEqual(classify("从Lira开始")["stage"], "06")
        self.assertEqual(classify("只做表演")["stage"], "07")
        self.assertEqual(classify("只做CINEDANCE")["kind"], "direct_entry")

    def test_stage_commands(self) -> None:
        self.assertEqual(classify("写剧本")["stage"], "05")
        self.assertEqual(classify("角色圣经")["stage"], "02")
        self.assertEqual(classify("分场大纲")["stage"], "04")
        self.assertEqual(classify("镜头规划")["stage"], "08")

    def test_entry_candidates(self) -> None:
        self.assertEqual(classify("从零开始做一部短片")["entry"], "A")
        self.assertEqual(classify("我有完整剧本")["entry"], "B")
        self.assertEqual(classify("只有大纲")["entry"], "C")
        self.assertEqual(classify("高手模式")["entry"], "D")

    def test_revision_and_unknown(self) -> None:
        self.assertEqual(classify("回到剧本阶段修改第8场")["kind"], "revision")
        result = classify("今天天气不错")
        self.assertEqual(result["kind"], "unknown")
        self.assertEqual(result["matched"], "")

    def test_whitespace_and_case_insensitive(self) -> None:
        self.assertEqual(normalize(" 调用 本地 知识库 "), "调用本地知识库")
        self.assertEqual(classify("调用 本地 知识库")["kind"], "knowledge")
        self.assertEqual(classify("只做 cinedance")["stage"], "08")

    def test_route_alias(self) -> None:
        self.assertEqual(route("从零开始"), classify("从零开始"))

    def test_bad_rules_path_raises(self) -> None:
        with self.assertRaises(IntentError):
            load_rules(REPO_ROOT / "content" / "not-exist.json")


if __name__ == "__main__":
    unittest.main()
