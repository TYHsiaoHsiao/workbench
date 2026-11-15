"""流程模板：加载、实例化与参数填充。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import (  # noqa: E402
    TemplateError,
    get_template,
    instantiate,
    instantiate_template,
    load_templates,
)


class FlowTemplatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        report = create_project("模板测试", base=base / "projects")
        self.project = Path(report["path"])

    def test_load_templates(self) -> None:
        templates = load_templates()
        self.assertEqual(4, len(templates))
        ids = [item["template_id"] for item in templates]
        self.assertEqual(["tpl-full-flow", "tpl-relay", "tpl-knowledge", "tpl-style"], ids)
        for item in templates:
            self.assertIn("nodes", item["graph"])
            self.assertGreaterEqual(len(item["graph"]["nodes"]), 2)

    def test_get_unknown_template_raises(self) -> None:
        with self.assertRaises(TemplateError):
            get_template("tpl-missing")

    def test_instantiate_rewrites_identity(self) -> None:
        template = get_template("tpl-knowledge")
        graph = instantiate(template, self.project.name, graph_id="tpl-copy", name="知识增强流程")
        self.assertEqual("tpl-copy", graph["graph_id"])
        self.assertEqual(self.project.name, graph["project"])
        self.assertEqual("知识增强流程", graph["name"])
        start = next(node for node in graph["nodes"] if node["type"] == "start")
        self.assertEqual(self.project.name, start["params"]["project"])

    def test_instantiate_does_not_mutate_template(self) -> None:
        template = get_template("tpl-full-flow")
        before = template["graph"]["graph_id"]
        instance = instantiate(template, self.project.name, graph_id="flow-copy", name="复制")
        instance["nodes"][0]["label"] = "被修改"
        template_again = get_template("tpl-full-flow")
        self.assertEqual(before, template_again["graph"]["graph_id"])
        self.assertNotEqual("被修改", template_again["graph"]["nodes"][0]["label"])

    def test_instantiate_by_id(self) -> None:
        graph = instantiate_template("tpl-style", self.project.name, graph_id="style-copy", name="风格流程")
        self.assertEqual("style-copy", graph["graph_id"])
        self.assertEqual("风格流程", graph["name"])

    def test_instantiate_unknown_raises(self) -> None:
        with self.assertRaises(TemplateError):
            instantiate_template("tpl-missing", self.project.name)


if __name__ == "__main__":
    unittest.main()
