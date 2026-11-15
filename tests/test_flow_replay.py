"""运行回放：时间线/耗时/失败定位，以及 CLI 图导入导出。"""
from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from flow import (  # noqa: E402
    build_replay,
    format_replay_text,
    instantiate_template,
    read_graph_data,
    write_graph_data,
)

cli_main = importlib.import_module("cli.main")


def fake_run(steps: list[dict], status: str = "succeeded") -> dict:
    return {
        "contract_version": "0.1",
        "run_id": "run-test-0001",
        "graph_id": "flow-test",
        "project": "回放测试",
        "status": status,
        "mode": "full",
        "dry_run": False,
        "started_at": "2026-11-15T10:00:00+08:00",
        "finished_at": "2026-11-15T10:00:02+08:00",
        "steps": steps,
    }


def step(node_id: str, status: str, start: str, end: str, **extra) -> dict:
    data = {"node_id": node_id, "status": status, "started_at": start, "ended_at": end}
    data.update(extra)
    return data


GRAPH = {
    "nodes": [
        {"id": "start", "type": "start", "label": "开始"},
        {"id": "stage-01", "type": "stage", "label": "01 概念锚定"},
        {"id": "end", "type": "end", "label": "结束"},
    ]
}


class FlowReplayTest(unittest.TestCase):
    def test_build_replay_timeline(self) -> None:
        run = fake_run(
            [
                step("start", "succeeded", "2026-11-15T10:00:00+08:00", "2026-11-15T10:00:00.500+08:00"),
                step(
                    "stage-01",
                    "succeeded",
                    "2026-11-15T10:00:00.500+08:00",
                    "2026-11-15T10:00:01.500+08:00",
                    outputs=["stage 01 完成"],
                ),
                step("end", "succeeded", "2026-11-15T10:00:01.500+08:00", "2026-11-15T10:00:02+08:00"),
            ]
        )
        replay = build_replay(run, GRAPH)
        self.assertEqual("run-test-0001", replay["run_id"])
        self.assertEqual(3, len(replay["steps"]))
        self.assertEqual(500, replay["steps"][0]["duration_ms"])
        self.assertEqual(1000, replay["steps"][1]["duration_ms"])
        self.assertEqual("01 概念锚定", replay["steps"][1]["label"])
        self.assertEqual(2000, replay["total_duration_ms"])
        self.assertEqual(2000, replay["step_duration_ms"])
        self.assertEqual("stage-01", replay["slowest_node_id"])
        self.assertIsNone(replay["failed_node_id"])
        self.assertEqual(3, replay["counts"]["succeeded"])

    def test_build_replay_failure(self) -> None:
        run = fake_run(
            [
                step("start", "succeeded", "2026-11-15T10:00:00+08:00", "2026-11-15T10:00:00.200+08:00"),
                step(
                    "stage-01",
                    "failed",
                    "2026-11-15T10:00:00.200+08:00",
                    "2026-11-15T10:00:00.900+08:00",
                    error="门禁未通过，不能推进",
                ),
            ],
            status="failed",
        )
        replay = build_replay(run, GRAPH)
        self.assertEqual("stage-01", replay["failed_node_id"])
        self.assertIn("门禁未通过", replay["failed_error"])
        self.assertEqual(1, replay["counts"]["failed"])

    def test_format_replay_text(self) -> None:
        run = fake_run(
            [step("start", "succeeded", "2026-11-15T10:00:00+08:00", "2026-11-15T10:00:00.100+08:00")]
        )
        text = format_replay_text(build_replay(run, GRAPH))
        self.assertIn("run-test-0001", text)
        self.assertIn("start", text)
        self.assertIn("100ms", text)


class FlowImportExportCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        report = create_project("导入导出测试", base=base / "projects")
        self.project = Path(report["path"])
        graph = instantiate_template("tpl-knowledge", self.project.name, graph_id="io-flow", name="导入导出流程")
        write_graph_data(self.project, graph)

    def test_export_import_roundtrip(self) -> None:
        out = Path(self.tmp.name) / "exported.json"
        code = cli_main.cmd_flow_export(
            argparse.Namespace(project=str(self.project), graph="io-flow", file=None, out=str(out))
        )
        self.assertEqual(0, code)
        self.assertTrue(out.is_file())
        code = cli_main.cmd_flow_import(
            argparse.Namespace(
                project=str(self.project), file=str(out), graph="io-imported", force=False, json=True
            )
        )
        self.assertEqual(0, code)
        data = read_graph_data(self.project, "io-imported")
        self.assertEqual("io-imported", data["graph_id"])
        self.assertEqual(self.project.name, data["project"])
        self.assertEqual(5, len(data["nodes"]))

    def test_import_missing_file_fails(self) -> None:
        code = cli_main.cmd_flow_import(
            argparse.Namespace(
                project=str(self.project),
                file=str(Path(self.tmp.name) / "missing.json"),
                graph=None,
                force=False,
                json=True,
            )
        )
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
