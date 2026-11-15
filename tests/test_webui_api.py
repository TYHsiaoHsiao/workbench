"""本地 Web 服务 API：静态页面 / 流程图 / 校验 / 运行 / 确认 / 令牌。"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project, load_state  # noqa: E402
from flow import write_graph_data  # noqa: E402
from webui import create_server  # noqa: E402
from webui.server import WorkbenchHandler  # noqa: E402

WorkbenchHandler.quiet = True


def make_node(node_id: str, node_type: str, stage: str | None = None, x: int = 0) -> dict:
    params: dict = {}
    if node_type == "start":
        params = {"project": "接口测试", "entry": "A"}
    elif node_type == "stage":
        params = {"stage": stage or "01", "auto_gates": True}
    elif node_type == "confirm":
        params = {"prompt": "确认继续"}
    return {
        "id": node_id,
        "type": node_type,
        "label": node_type,
        "position": {"x": x, "y": 140},
        "params": params,
    }


def edge(edge_id: str, from_node: str, from_port: str, to_node: str, to_port: str) -> dict:
    return {
        "id": edge_id,
        "from": {"node": from_node, "port": from_port},
        "to": {"node": to_node, "port": to_port},
    }


def make_graph(project: str, with_confirm: bool = False) -> dict:
    if with_confirm:
        nodes = [
            make_node("start", "start"),
            make_node("stage-01", "stage", "01", x=320),
            make_node("confirm-01", "confirm", x=540),
            make_node("end", "end", x=760),
        ]
        edges = [
            edge("e1", "start", "project", "stage-01", "state"),
            edge("e2", "stage-01", "artifact", "confirm-01", "artifact"),
            edge("e3", "confirm-01", "confirmed", "end", "any"),
        ]
    else:
        nodes = [
            make_node("start", "start"),
            make_node("stage-01", "stage", "01", x=320),
            make_node("end", "end", x=640),
        ]
        edges = [
            edge("e1", "start", "project", "stage-01", "state"),
            edge("e2", "stage-01", "artifact", "end", "any"),
        ]
    return {
        "contract_version": "0.1",
        "graph_id": "flow-test",
        "name": "接口测试流程",
        "project": project,
        "created_at": "2026-11-15T00:00:00+08:00",
        "updated_at": "2026-11-15T00:00:00+08:00",
        "nodes": nodes,
        "edges": edges,
        "settings": {"auto_advance": True, "allow_skip_stages": False, "dry_run_first": True},
    }


class WebUIClient:
    def __init__(self, server) -> None:
        self.server = server
        host, port = server.server_address[:2]
        self.base = f"http://127.0.0.1:{port}"

    def request(self, method: str, path: str, body=None, token: str | None = None) -> tuple[int, bytes]:
        data = None
        headers: dict[str, str] = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Workbench-Token"] = token
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def json(self, method: str, path: str, body=None, token: str | None = None):
        status, raw = self.request(method, path, body, token)
        return status, json.loads(raw.decode("utf-8"))


class WebUIApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name) / "projects"
        report = create_project("接口测试", base=base)
        self.project = Path(report["path"])
        self.graph = make_graph(self.project.name)
        write_graph_data(self.project, self.graph)
        self.server = create_server(self.project, port=0, use_token=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        self.client = WebUIClient(self.server)

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _q(self, path: str) -> str:
        joiner = "&" if "?" in path else "?"
        return path + joiner + "project=" + quote(str(self.project))

    def test_static_index(self) -> None:
        status, raw = self.client.request("GET", "/")
        self.assertEqual(200, status)
        html = raw.decode("utf-8")
        self.assertIn("可视化节点工作台", html)
        self.assertIn("/app.js", html)
        self.assertEqual(200, self.client.request("GET", "/app.js")[0])
        self.assertEqual(200, self.client.request("GET", "/style.css")[0])

    def test_workbench_info_and_projects(self) -> None:
        status, data = self.client.json("GET", self._q("/api/workbench"))
        self.assertEqual(200, status)
        self.assertEqual("接口测试", data["project_name"])
        self.assertIn("version", data)
        status, data = self.client.json("GET", "/api/projects")
        self.assertEqual(200, status)
        self.assertIsInstance(data["projects"], list)
        entry = data["projects"][0]
        for key in ("artifacts", "pending_gates", "workflows", "runs", "last_run"):
            self.assertIn(key, entry)

    def test_node_types(self) -> None:
        status, data = self.client.json("GET", "/api/node-types")
        self.assertEqual(200, status)
        self.assertEqual(10, len(data["types"]))
        self.assertEqual("0.1", data["contract_version"])

    def test_workflow_get(self) -> None:
        status, data = self.client.json("GET", self._q("/api/workflows"))
        self.assertEqual(200, status)
        self.assertEqual("flow-test", data["graphs"][0]["graph_id"])
        status, data = self.client.json("GET", self._q("/api/workflows/flow-test"))
        self.assertEqual(200, status)
        self.assertEqual(3, len(data["graph"]["nodes"]))

    def test_workflow_put_roundtrip(self) -> None:
        graph = json.loads(json.dumps(self.graph))
        graph["nodes"][1]["label"] = "阶段 01（改）"
        status, data = self.client.json("PUT", self._q("/api/workflows/flow-test"), {"graph": graph})
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        status, data = self.client.json("GET", self._q("/api/workflows/flow-test"))
        self.assertEqual("阶段 01（改）", data["graph"]["nodes"][1]["label"])

    def test_workflow_put_invalid_rejected(self) -> None:
        graph = json.loads(json.dumps(self.graph))
        graph["edges"][0]["to"] = {"node": "stage-01", "port": "text"}
        status, data = self.client.json("PUT", self._q("/api/workflows/flow-test"), {"graph": graph})
        self.assertEqual(422, status)
        self.assertFalse(data["ok"])
        self.assertTrue(data["errors"])

    def test_validate_endpoint(self) -> None:
        status, data = self.client.json("POST", "/api/workflows/validate", {"graph": self.graph})
        self.assertEqual(200, status)
        self.assertTrue(data["ok"], msg=data)
        bad = json.loads(json.dumps(self.graph))
        bad["edges"][1]["to"] = {"node": "end", "port": "any"}
        bad["edges"][1]["from"] = {"node": "start", "port": "project"}
        status, data = self.client.json("POST", "/api/workflows/validate", {"graph": bad})
        self.assertEqual(200, status)
        self.assertFalse(data["ok"])

    def test_run_dry_run_via_api(self) -> None:
        before = load_state(self.project)
        status, data = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "mode": "full", "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("succeeded", data["run"]["status"])
        self.assertEqual(["planned", "planned", "planned"], [step["status"] for step in data["run"]["steps"]])
        after = load_state(self.project)
        self.assertEqual(before["stage"], after["stage"])

    def test_run_live_advances(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": False},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("succeeded", data["run"]["status"])
        self.assertEqual("02", load_state(self.project)["stage"])

    def test_confirm_via_api(self) -> None:
        confirm_graph = make_graph(self.project.name, with_confirm=True)
        write_graph_data(self.project, confirm_graph)
        status, data = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": False},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("awaiting_confirm", data["run"]["status"])
        run_id = data["run"]["run_id"]
        self.assertTrue(data.get("awaiting"))
        status, data = self.client.json(
            "POST", f"/api/runs/{run_id}/confirm", {"approved": True, "note": "接口确认"}
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("succeeded", data["run"]["status"])

    def test_templates_endpoint(self) -> None:
        status, data = self.client.json("GET", "/api/templates")
        self.assertEqual(200, status)
        self.assertEqual(4, len(data["templates"]))
        ids = {item["template_id"] for item in data["templates"]}
        self.assertEqual({"tpl-full-flow", "tpl-relay", "tpl-knowledge", "tpl-style"}, ids)

    def test_new_from_template(self) -> None:
        status, data = self.client.json(
            "POST",
            self._q("/api/workflows/new"),
            {"name": "模板流程", "graph_id": "tpl-test", "template_id": "tpl-knowledge"},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("tpl-test", data["graph_id"])
        self.assertEqual(5, len(data["graph"]["nodes"]))
        status, data = self.client.json("GET", self._q("/api/workflows/tpl-test"))
        self.assertEqual(200, status)
        self.assertEqual("模板流程", data["graph"]["name"])

    def test_runs_list_endpoint(self) -> None:
        self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": True},
        )
        status, data = self.client.json("GET", self._q("/api/runs?limit=5"))
        self.assertEqual(200, status)
        self.assertGreaterEqual(len(data["runs"]), 1)
        self.assertIn("run_id", data["runs"][0])

    def test_batch_endpoint_dry_run(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/runs/batch",
            {"project": str(self.project), "dry_run": True, "auto_confirm": True},
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        self.assertGreaterEqual(data["count"], 1)

    def test_replay_endpoint(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        run_id = data["run"]["run_id"]
        status, data = self.client.json("GET", self._q(f"/api/runs/{run_id}/replay"))
        self.assertEqual(200, status, msg=data)
        replay = data["replay"]
        self.assertEqual(run_id, replay["run_id"])
        self.assertEqual(3, len(replay["steps"]))
        for item in replay["steps"]:
            self.assertIn("duration_ms", item)
            self.assertIn("label", item)
        self.assertIn("total_duration_ms", replay)

    def test_workflow_import_endpoint(self) -> None:
        graph = json.loads(json.dumps(self.graph))
        graph["name"] = "外部导入流程"
        status, data = self.client.json(
            "POST",
            "/api/workflows/import",
            {"project": str(self.project), "graph": graph, "graph_id": "imported-flow"},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("imported-flow", data["graph_id"])
        status, data = self.client.json("GET", self._q("/api/workflows/imported-flow"))
        self.assertEqual(200, status)
        self.assertEqual("外部导入流程", data["graph"]["name"])
        status, data = self.client.json(
            "POST",
            "/api/workflows/import",
            {"project": str(self.project), "graph": {"contract_version": "0.1", "graph_id": "bad"}},
        )
        self.assertEqual(422, status)
        self.assertFalse(data["ok"])

    def test_unknown_api_404(self) -> None:
        status, _ = self.client.request("GET", self._q("/api/unknown"))
        self.assertEqual(404, status)

    def test_project_summary_endpoint(self) -> None:
        status, data = self.client.json(
            "GET", f"/api/projects/{quote(str(self.project))}/summary"
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        self.assertEqual("接口测试", data["project"])
        self.assertIsInstance(data["artifacts"], list)
        self.assertIsInstance(data["graphs"], list)
        self.assertGreaterEqual(len(data["graphs"]), 1)
        self.assertIn("nodes", data["graphs"][0])
        self.assertIn("edges", data["graphs"][0])

    def test_run_diff_endpoint(self) -> None:
        first = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": True},
        )
        self.assertEqual(200, first[0], msg=first[1])
        run_one = first[1]["run"]["run_id"]
        second = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": True},
        )
        self.assertEqual(200, second[0], msg=second[1])
        run_two = second[1]["run"]["run_id"]

        status, data = self.client.json(
            "GET", self._q(f"/api/runs/{run_two}/diff") + "&other=" + quote(run_one)
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        diff = data["diff"]
        self.assertIn("summary", diff)
        self.assertIn("node_changes", diff)
        self.assertEqual(3, diff["summary"]["base_steps"])
        self.assertEqual(3, diff["summary"]["target_steps"])

    def test_token_required(self) -> None:
        server = create_server(self.project, port=0, use_token=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=5)))
        client = WebUIClient(server)
        status, _ = client.request("GET", "/api/node-types")
        self.assertEqual(401, status)
        status, data = client.json("GET", "/api/node-types", token=server.token)
        self.assertEqual(200, status)
        self.assertEqual(10, len(data["types"]))


if __name__ == "__main__":
    unittest.main()
