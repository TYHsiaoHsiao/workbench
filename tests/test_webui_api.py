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
from unittest import mock
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project, load_state  # noqa: E402
from flow import write_graph_data  # noqa: E402
from generate.jobs import create_job, update_job  # noqa: E402
from webui import create_server  # noqa: E402
from webui.server import STATIC_DIR, WorkbenchHandler  # noqa: E402

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
        self.assertEqual(17, len(data["types"]))
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

    def test_workflows_batch_endpoint_and_history(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/workflows/batch",
            {
                "project": str(self.project),
                "dry_run": True,
                "auto_confirm": True,
                "auto_retry": 1,
            },
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        batch = data["batch"]
        self.assertTrue(batch["batch_id"].startswith("batch-"), msg=batch)
        self.assertGreaterEqual(batch["summary"]["total"], 1)
        self.assertEqual(1, batch["auto_retry"])
        batch_id = batch["batch_id"]
        status, data = self.client.json("GET", self._q("/api/batches?limit=5"))
        self.assertEqual(200, status)
        self.assertIn(batch_id, [item["batch_id"] for item in data["batches"]])
        status, data = self.client.json("GET", self._q(f"/api/batches/{batch_id}"))
        self.assertEqual(200, status, msg=data)
        self.assertEqual(batch_id, data["batch"]["batch_id"])
        self.assertEqual(1, len(data["batch"]["graphs"]))

    def test_workflows_batch_parallel_endpoint(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/workflows/batch",
            {
                "project": str(self.project),
                "dry_run": True,
                "parallel": True,
                "workers": 2,
            },
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        batch = data["batch"]
        self.assertTrue(batch["parallel"])
        self.assertEqual(2, batch["workers"])

    def test_batches_report_endpoint(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/workflows/batch",
            {"project": str(self.project), "dry_run": True, "auto_confirm": True},
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        status, data = self.client.json("GET", self._q("/api/batches/report?limit=5&format=md"))
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        self.assertEqual("md", data["format"])
        self.assertGreaterEqual(data["summary"]["batches"], 1)
        self.assertIn("批次趋势报表", data["text"])
        self.assertIn("success_rate", data["summary"])
        status, data = self.client.json("GET", self._q("/api/batches/report?limit=5&format=csv"))
        self.assertEqual(200, status, msg=data)
        self.assertEqual("csv", data["format"])
        self.assertTrue(data["text"].splitlines()[0].startswith("batch_id,"), msg=data["text"][:120])
        # M35: HTML report endpoint
        status, data = self.client.json("GET", self._q("/api/batches/report?limit=5&format=html"))
        self.assertEqual(200, status, msg=data)
        self.assertEqual("html", data["format"])
        self.assertIn("<!DOCTYPE html>", data["text"])
        self.assertIn("批次趋势报表", data["text"])
        self.assertIn("<style>", data["text"])

    def test_batches_trend_endpoint(self) -> None:
        # M37：批次趋势 SVG 端点
        status, data = self.client.json(
            "POST",
            "/api/workflows/batch",
            {"project": str(self.project), "dry_run": True, "auto_confirm": True},
        )
        self.assertEqual(200, status, msg=data)
        status, data = self.client.json("GET", self._q("/api/batches/trend?limit=5"))
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        self.assertIn("<svg", data["svg"])
        self.assertIn("批次趋势", data["svg"])
        self.assertGreaterEqual(data["summary"]["batches"], 1)

    def test_batches_report_push_endpoint(self) -> None:
        # M36：批次报表推送端点（webhook 由 mock 捕获）
        from unittest import mock as _mock

        status, data = self.client.json(
            "POST",
            "/api/workflows/batch",
            {"project": str(self.project), "dry_run": True, "auto_confirm": True},
        )
        self.assertEqual(200, status, msg=data)
        captured: dict = {}

        def fake_notify(url, payload, *, format="generic", retries=0):
            captured["url"] = url
            captured["payload"] = payload
            return {"configured": True, "ok": True, "format": format, "attempts": 1, "status_code": 200, "error": ""}

        with _mock.patch("flow.notify.notify_webhook", fake_notify):
            status, data = self.client.json(
                "POST",
                "/api/batches/report/push",
                {"project": str(self.project), "webhook_url": "https://example.test/hook", "limit": 5, "format": "md"},
            )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        self.assertEqual("batch.report", captured["payload"]["event"])
        self.assertEqual(200, data["webhook"]["status_code"])
        self.assertGreaterEqual(data["summary"]["batches"], 1)
        # 缺少 webhook_url → 400
        status, data = self.client.json(
            "POST",
            "/api/batches/report/push",
            {"project": str(self.project)},
        )
        self.assertEqual(400, status, msg=data)

    def test_batch_recover_endpoint(self) -> None:
        broken = json.loads(json.dumps(self.graph))
        broken["graph_id"] = "flow-broken"
        broken["edges"] = []
        write_graph_data(self.project, broken)
        status, data = self.client.json(
            "POST",
            "/api/workflows/batch",
            {"project": str(self.project), "dry_run": True, "graph_ids": ["flow-broken"]},
        )
        self.assertEqual(200, status, msg=data)
        self.assertFalse(data["ok"], msg=data)
        batch_id = data["batch"]["batch_id"]
        self.assertEqual(1, data["batch"]["summary"]["failed"])
        broken["edges"] = json.loads(json.dumps(self.graph))["edges"]
        write_graph_data(self.project, broken)
        status, data = self.client.json(
            "POST",
            f"/api/batches/{batch_id}/recover",
            {"project": str(self.project)},
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        self.assertEqual(1, data["recovered"])
        self.assertEqual("succeeded", data["batch"]["status"])
        self.assertEqual(0, data["batch"]["summary"]["failed"])

    def test_queue_endpoints(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/queue",
            {"project": str(self.project), "all": True, "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        queue_id = data["entry"]["queue_id"]
        self.assertEqual("pending", data["entry"]["status"])
        status, data = self.client.json("GET", self._q("/api/queue"))
        self.assertEqual(200, status, msg=data)
        self.assertIn(queue_id, [item["queue_id"] for item in data["entries"]])
        status, data = self.client.json(
            "POST",
            "/api/queue/run",
            {"project": str(self.project), "limit": 5},
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"], msg=data)
        self.assertEqual(1, data["summary"]["succeeded"])

    def test_queue_run_endpoint_failure_notification(self) -> None:
        broken = json.loads(json.dumps(self.graph))
        broken["graph_id"] = "flow-queue-broken"
        broken["edges"] = []
        write_graph_data(self.project, broken)
        status, data = self.client.json(
            "POST",
            "/api/queue",
            {"project": str(self.project), "graph_ids": ["flow-queue-broken"], "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        status, data = self.client.json(
            "POST",
            "/api/queue/run",
            {"project": str(self.project), "limit": 5},
        )
        self.assertEqual(200, status, msg=data)
        self.assertFalse(data["ok"], msg=data)
        self.assertEqual(1, data["summary"]["failed"])
        entry = data["ran"][0]
        self.assertEqual("failed", entry["status"])
        self.assertIn("flow-queue-broken", entry["notification"]["failed_graphs"])

    def test_queue_cancel_and_schedule_endpoint(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/queue",
            {
                "project": str(self.project),
                "graph_ids": [self.graph["graph_id"]],
                "dry_run": True,
                "scheduled_at": "2999-01-01T00:00",
            },
        )
        self.assertEqual(200, status, msg=data)
        entry = data["entry"]
        self.assertIn("scheduled_at", entry)
        self.assertGreater(entry["order"], -1)
        status, data = self.client.json(
            "POST",
            f"/api/queue/{entry['queue_id']}/cancel",
            {"project": str(self.project)},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("canceled", data["entry"]["status"])
        status, data = self.client.json("GET", self._q("/api/queue") + "&status=canceled")
        self.assertEqual(200, status, msg=data)
        self.assertIn(entry["queue_id"], [item["queue_id"] for item in data["entries"]])

    def test_queue_move_endpoint(self) -> None:
        ids = []
        for _ in range(2):
            status, data = self.client.json(
                "POST",
                "/api/queue",
                {"project": str(self.project), "graph_ids": [self.graph["graph_id"]], "dry_run": True},
            )
            self.assertEqual(200, status, msg=data)
            ids.append(data["entry"]["queue_id"])
        status, data = self.client.json(
            "POST",
            f"/api/queue/{ids[1]}/move",
            {"project": str(self.project), "index": 0},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual(0, data["move"]["order"])
        status, data = self.client.json("GET", self._q("/api/queue"))
        self.assertEqual(200, status, msg=data)
        orders = {item["queue_id"]: item.get("order") for item in data["entries"]}
        self.assertEqual(0, orders[ids[1]])
        self.assertEqual(1, orders[ids[0]])

    def test_rollback_endpoints(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/rollback/create",
            {"project": str(self.project), "label": "web 快照"},
        )
        self.assertEqual(200, status, msg=data)
        snapshot_id = data["snapshot"]["snapshot_id"]
        self.assertTrue(snapshot_id.startswith("snap-"))
        status, data = self.client.json("GET", self._q("/api/rollback/snapshots"))
        self.assertEqual(200, status, msg=data)
        self.assertIn(snapshot_id, [row["snapshot_id"] for row in data["snapshots"]])
        status, data = self.client.json(
            "POST",
            "/api/rollback/apply",
            {"project": str(self.project), "snapshot": snapshot_id, "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["rollback"]["dry_run"])
        status, data = self.client.json(
            "POST",
            "/api/rollback/apply",
            {"project": str(self.project), "snapshot": snapshot_id},
        )
        self.assertEqual(200, status, msg=data)
        self.assertFalse(data["rollback"]["dry_run"])
        self.assertTrue(data["rollback"]["restored_files"])
        self.assertTrue(str(data["rollback"]["safety_snapshot"]).startswith("snap-"))

    def test_queue_retry_and_notifications_endpoint(self) -> None:
        broken = json.loads(json.dumps(self.graph))
        broken["graph_id"] = "flow-queue-retry"
        broken["edges"] = []
        write_graph_data(self.project, broken)
        status, data = self.client.json(
            "POST",
            "/api/queue",
            {"project": str(self.project), "graph_ids": ["flow-queue-retry"], "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        queue_id = data["entry"]["queue_id"]
        status, data = self.client.json(
            "POST",
            "/api/queue/run",
            {"project": str(self.project), "limit": 5},
        )
        self.assertEqual(200, status, msg=data)
        self.assertFalse(data["ok"], msg=data)
        status, data = self.client.json("GET", self._q("/api/queue/notifications") + "&limit=5")
        self.assertEqual(200, status, msg=data)
        self.assertEqual(1, len(data["notifications"]), msg=data)
        self.assertIn("flow-queue-retry", data["notifications"][0]["failed_graphs"])
        status, data = self.client.json(
            "POST",
            f"/api/queue/{queue_id}/retry",
            {"project": str(self.project)},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("pending", data["entry"]["status"])
        self.assertEqual(1, data["entry"]["attempts"])

    def test_queue_run_retry_failed_endpoint(self) -> None:
        broken = json.loads(json.dumps(self.graph))
        broken["graph_id"] = "flow-queue-retry2"
        broken["edges"] = []
        write_graph_data(self.project, broken)
        status, data = self.client.json(
            "POST",
            "/api/queue",
            {"project": str(self.project), "graph_ids": ["flow-queue-retry2"], "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        queue_id = data["entry"]["queue_id"]
        status, data = self.client.json(
            "POST",
            "/api/queue/run",
            {"project": str(self.project), "limit": 5},
        )
        self.assertFalse(data["ok"], msg=data)
        status, data = self.client.json(
            "POST",
            "/api/queue/run",
            {"project": str(self.project), "limit": 5, "retry_failed": 1},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual([queue_id], data["retried"], msg=data)
        self.assertFalse(data["ok"], msg=data)
        status, data = self.client.json("GET", self._q("/api/queue/notifications") + "&limit=5")
        self.assertEqual(200, status, msg=data)
        self.assertEqual(2, len(data["notifications"]), msg=data)

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

    def test_baseline_endpoints(self) -> None:
        status, data = self.client.json(
            "POST",
            "/api/runs",
            {"project": str(self.project), "graph_id": "flow-test", "dry_run": True},
        )
        self.assertEqual(200, status, msg=data)
        run_id = data["run"]["run_id"]
        status, data = self.client.json(
            "POST", "/api/workflows/flow-test/baseline", {"project": str(self.project), "run_id": run_id}
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual(run_id, data["baseline"]["run_id"])
        status, data = self.client.json("GET", self._q("/api/workflows/flow-test/baseline"))
        self.assertEqual(200, status, msg=data)
        self.assertEqual(run_id, data["baseline"]["run_id"])
        status, data = self.client.json(
            "POST", "/api/workflows/flow-test/baseline/clear", {"project": str(self.project)}
        )
        self.assertEqual(200, status, msg=data)
        status, data = self.client.json("GET", self._q("/api/workflows/flow-test/baseline"))
        self.assertEqual(200, status, msg=data)
        self.assertIsNone(data["baseline"])

    def test_artifacts_snapshot_and_diff_endpoints(self) -> None:
        story = self.project / "01_story" / "synopsis.md"
        story.parent.mkdir(parents=True, exist_ok=True)
        story.write_text("# 大纲\n第一版\n", encoding="utf-8")
        status, data = self.client.json(
            "POST",
            f"/api/projects/{quote(str(self.project))}/artifacts/snapshot",
            {"label": "接口快照"},
        )
        self.assertEqual(200, status, msg=data)
        snapshot_id = data["snapshot"]["snapshot_id"]
        status, data = self.client.json(
            "GET", f"/api/projects/{quote(str(self.project))}/artifacts/snapshots"
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual(snapshot_id, data["snapshots"][0]["snapshot_id"])
        story.write_text("# 大纲\n第二版\n", encoding="utf-8")
        status, data = self.client.json(
            "GET", f"/api/projects/{quote(str(self.project))}/artifacts/diff?base={quote(snapshot_id)}"
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual(1, data["diff"]["summary"]["changed"])
        self.assertIn("产物差异", data["text"])

    def test_project_summary_cache(self) -> None:
        url = f"/api/projects/{quote(str(self.project))}/summary"
        status, first = self.client.json("GET", url)
        self.assertEqual(200, status, msg=first)
        self.assertFalse(first.get("cached", False))
        status, second = self.client.json("GET", url)
        self.assertEqual(200, status, msg=second)
        self.assertTrue(second.get("cached", False))
        status, refreshed = self.client.json("GET", url + "?refresh=1")
        self.assertEqual(200, status, msg=refreshed)
        self.assertFalse(refreshed.get("cached", False))

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
        self.assertEqual(17, len(data["types"]))


    def test_generate_providers_endpoint(self) -> None:
        status, data = self.client.json("GET", "/api/generate/providers")
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        ids = [item["provider_id"] for item in data["providers"]]
        self.assertEqual(["mock", "seedance_2_0", "seedance_2_5", "minimax_h3"], ids)
        entry = next(item for item in data["providers"] if item["provider_id"] == "seedance_2_5")
        self.assertEqual("video", entry["kind"])
        self.assertIn("seedance-2.5", entry["models"])
        self.assertEqual("SEEDANCE_API_KEY", entry["env_key"])

    def test_generate_plan_and_job_flow(self) -> None:
        prompt = self.project / "05_shots" / "shot-01-prompt.md"
        prompt.write_text("画面：雨夜霓虹街头，女性侦探背影缓步前行，镜头缓推。\n", encoding="utf-8")
        relative = str(prompt.relative_to(self.project))
        status, data = self.client.json(
            "POST",
            "/api/generate/plan",
            {"provider": "seedance_2_5", "prompt_path": relative, "shot": "1-01"},
        )
        self.assertEqual(200, status, msg=data)
        plan = data["plan"]
        self.assertEqual("seedance_2_5", plan["provider"])
        self.assertTrue(plan["dry_run"])
        self.assertGreater(plan["chars"], 0)
        self.assertEqual(64, len(plan["prompt_sha256"]))
        status, data = self.client.json(
            "POST",
            "/api/generate/jobs",
            {"provider": "mock", "prompt_path": relative, "shot": "1-01", "live": False},
        )
        self.assertEqual(200, status, msg=data)
        job = data["job"]
        self.assertEqual("dry_run", job["status"])
        self.assertTrue(job["dry_run"])
        job_id = job["job_id"]
        status, data = self.client.json("GET", self._q(f"/api/generate/jobs/{job_id}"))
        self.assertEqual(200, status, msg=data)
        self.assertEqual(job_id, data["job"]["job_id"])
        status, data = self.client.json("GET", self._q("/api/generate/jobs?limit=5"))
        self.assertEqual(200, status, msg=data)
        self.assertIn(job_id, [item["job_id"] for item in data["jobs"]])

    def test_generate_plan_invalid_rejected(self) -> None:
        status, data = self.client.json(
            "POST", "/api/generate/plan", {"provider": "unknown_platform", "prompt_text": "x"}
        )
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])
        self.assertTrue(data["error"])

    def _submitted_job(self, response: dict | None = None) -> dict:
        prompt = self.project / "05_shots" / "shot-01-prompt.md"
        prompt.write_text("画面：雨夜霓虹街头，女性侦探背影缓行。\n", encoding="utf-8")
        relative = str(prompt.relative_to(self.project))
        job = create_job(
            self.project,
            provider="seedance_2_5",
            model="seedance-2.5",
            project=self.project.name,
            shot="1-01",
            prompt_path=relative,
            prompt_sha256="a" * 64,
            chars=20,
            dry_run=False,
            status="submitted",
        )
        if response is not None:
            job = update_job(self.project, job["job_id"], response=response)
        return job

    def test_generate_job_refresh_endpoint(self) -> None:
        job = self._submitted_job(response={"id": "platform-123"})
        with mock.patch(
            "generate.providers._http_status",
            return_value={"status": "succeeded", "video_url": "https://cdn.test/out.mp4"},
        ):
            status, data = self.client.json(
                "POST",
                f"/api/generate/jobs/{job['job_id']}/refresh",
                {"project": str(self.project)},
            )
        self.assertEqual(200, status, msg=data)
        self.assertEqual("succeeded", data["job"]["status"])
        self.assertEqual("https://cdn.test/out.mp4", data["job"]["response"]["video_url"])

    def test_generate_refresh_all_endpoint(self) -> None:
        first = self._submitted_job()
        second = self._submitted_job()
        with mock.patch(
            "generate.providers._http_status", return_value={"status": "running"}
        ):
            status, data = self.client.json(
                "POST", "/api/generate/jobs/refresh", {"project": str(self.project)}
            )
        self.assertEqual(200, status, msg=data)
        refreshed = {item["job_id"]: item for item in data["refreshed"]}
        self.assertEqual(2, len(refreshed))
        for job in (first, second):
            self.assertTrue(refreshed[job["job_id"]]["ok"])
            self.assertEqual("submitted", refreshed[job["job_id"]]["status"])


    def _terminal_job(self, status: str, response: dict | None = None) -> dict:
        prompt = self.project / "05_shots" / "shot-01-prompt.md"
        prompt.write_text("画面：雨夜霓虹街头，女性侦探背影缓行。\n", encoding="utf-8")
        relative = str(prompt.relative_to(self.project))
        job = create_job(
            self.project,
            provider="seedance_2_5",
            model="seedance-2.5",
            project=self.project.name,
            shot="1-01",
            prompt_path=relative,
            prompt_sha256="a" * 64,
            chars=20,
            dry_run=False,
            status=status,
        )
        if status == "failed":
            job = update_job(self.project, job["job_id"], error="平台拒绝")
        if response is not None:
            job = update_job(self.project, job["job_id"], response=response)
        return job

    def test_generate_job_retry_endpoint(self) -> None:
        job = self._terminal_job("failed")
        status, data = self.client.json(
            "POST",
            f"/api/generate/jobs/{job['job_id']}/retry",
            {"project": str(self.project), "live": False},
        )
        self.assertEqual(200, status, msg=data)
        new_job = data["job"]
        self.assertNotEqual(job["job_id"], new_job["job_id"])
        self.assertEqual(job["job_id"], new_job["retried_from"])
        self.assertTrue(new_job["dry_run"])

    def test_generate_job_adopt_endpoint(self) -> None:
        url = "https://cdn.test/adopted.mp4"
        job = self._terminal_job("succeeded", response={"video_url": url})
        status, data = self.client.json(
            "POST",
            f"/api/generate/jobs/{job['job_id']}/adopt",
            {"project": str(self.project), "stage": "05"},
        )
        self.assertEqual(200, status, msg=data)
        artifact = data["artifact"]
        self.assertTrue(artifact.startswith("05_shots/generations/"))
        self.assertTrue((self.project / artifact).is_file())
        status, detail = self.client.json(
            "GET", self._q(f"/api/generate/jobs/{job['job_id']}")
        )
        self.assertEqual(200, status, msg=detail)
        self.assertEqual(artifact, detail["job"]["adopted"]["artifact"])

    def test_generate_adopt_all_endpoint(self) -> None:
        first = self._terminal_job(
            "succeeded", response={"video_url": "https://cdn.test/batch1.mp4"}
        )
        second = self._terminal_job(
            "succeeded", response={"video_url": "https://cdn.test/batch2.mp4"}
        )
        failed = self._terminal_job("failed")
        status, data = self.client.json(
            "POST",
            "/api/generate/jobs/adopt",
            {"project": str(self.project), "stage": "05", "limit": 10},
        )
        self.assertEqual(200, status, msg=data)
        self.assertEqual(2, data["adopted_count"])
        items = {item["job_id"]: item for item in data["jobs"]}
        self.assertEqual({first["job_id"], second["job_id"]}, set(items))
        for job in (first, second):
            self.assertTrue(items[job["job_id"]]["ok"])
            artifact = items[job["job_id"]]["artifact"]
            self.assertTrue(artifact.startswith("05_shots/generations/"))
            self.assertTrue((self.project / artifact).is_file())
        self.assertNotIn(failed["job_id"], items)


    def test_dev_version_endpoint(self) -> None:
        status, data = self.client.json("GET", self._q("/api/dev/version"))
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["signature"], str)
        self.assertGreaterEqual(len(data["files"]), 3)
        self.assertIn("app.js", data["files"])
        self.assertIsInstance(data["latest_mtime_ns"], int)
        self.assertGreater(data["latest_mtime_ns"], 0)

    def test_dev_version_signature_changes_on_static_edit(self) -> None:
        _, first = self.client.json("GET", self._q("/api/dev/version"))
        probe = STATIC_DIR / "__live_preview_probe.txt"
        try:
            probe.write_text("probe", encoding="utf-8")
            _, second = self.client.json("GET", self._q("/api/dev/version"))
            self.assertNotEqual(first["signature"], second["signature"])
        finally:
            if probe.exists():
                probe.unlink()
        _, third = self.client.json("GET", self._q("/api/dev/version"))
        self.assertEqual(first["signature"], third["signature"])


    def test_http_error_paths(self) -> None:
        status, data = self.client.json("GET", "/api/does-not-exist")
        self.assertEqual(404, status)
        self.assertFalse(data["ok"])
        status, data = self.client.json("POST", "/api/does-not-exist", {})
        self.assertEqual(404, status)
        self.assertFalse(data["ok"])
        status, data = self.client.json("GET", self._q("/api/workflows/missing-flow"))
        self.assertEqual(400, status, msg=data)
        status, data = self.client.json("GET", self._q("/api/runs/run-does-not-exist"))
        self.assertEqual(400, status, msg=data)
        status, data = self.client.json("GET", self._q("/api/batches/batch-does-not-exist"))
        self.assertEqual(400, status, msg=data)
        status, data = self.client.json("POST", self._q("/api/queue"), {"graph_ids": []})
        self.assertEqual(400, status, msg=data)
        status, data = self.client.json("POST", "/api/queue/run", {})
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        status, data = self.client.json("POST", "/api/queue/q-missing/retry", {"project": str(self.project)})
        self.assertEqual(400, status, msg=data)
        status, data = self.client.json("POST", "/api/queue/q-missing/cancel", {"project": str(self.project)})
        self.assertEqual(400, status, msg=data)
        status, data = self.client.json("GET", "/api/queue/notifications")
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        status, raw = self.client.request("HEAD", "/")
        self.assertIn(status, (200, 404, 501), msg=raw)

    def test_m31_cron_preview_endpoint(self) -> None:
        status, data = self.client.json(
            "POST", "/api/cron/preview", {"expression": "*/5 * * * *", "count": 3}
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        self.assertEqual(3, len(data["next"]))
        status, data = self.client.json("POST", "/api/cron/preview", {"expression": "bad expr"})
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])

    def test_m31_queue_alerts_endpoint(self) -> None:
        path = self.project / "00_project" / "workflows" / "queue-notifications.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"at": "2026-11-16T09:00:00", "status": "failed", "message": "队列运行失败 2 条", '
            '"failed_graphs": ["g1", "g2"]}\n'
            '{"at": "2026-11-16T10:00:00", "status": "failed", "message": "队列运行失败 1 条", '
            '"failed_graphs": ["g1"]}\n',
            encoding="utf-8",
        )
        status, data = self.client.json("GET", self._q("/api/queue/alerts?limit=10"))
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        self.assertEqual(2, data["count"])
        self.assertEqual(
            [{"graph_id": "g1", "count": 2}, {"graph_id": "g2", "count": 1}],
            data["failed_graphs"],
        )
        status, data = self.client.json("GET", self._q("/api/queue/alerts"))
        self.assertEqual(200, status)
        self.assertEqual(2, data["count"])


    def test_ops_endpoints(self) -> None:
        status, data = self.client.json("GET", "/api/ops")
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        ops = data["ops"]
        self.assertGreaterEqual(len(ops), 15)
        by_id = {op["id"]: op for op in ops}
        self.assertIn("quickstart_demo", by_id)
        self.assertIn("project_list", by_id)
        self.assertTrue(by_id["rollback_apply"]["danger"])

        status, data = self.client.json(
            "POST", "/api/ops/run", {"op_id": "project_list", "params": {}}
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        self.assertTrue(data["result"]["ok"])
        self.assertEqual(0, data["result"]["exit_code"])

        status, data = self.client.json(
            "POST", "/api/ops/run", {"op_id": "quickstart_demo", "params": {}}
        )
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])

        status, data = self.client.json(
            "POST", "/api/ops/run", {"op_id": "no_such_op", "params": {}}
        )
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])

    def test_ops_history_and_batch_endpoints(self) -> None:
        status, data = self.client.json("GET", "/api/ops/history?limit=5")
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["history"], list)
        self.assertLessEqual(len(data["history"]), 5)

        status, data = self.client.json(
            "POST", "/api/ops/batch", {"items": [{"op_id": "project_list", "params": {}}]}
        )
        self.assertEqual(200, status, msg=data)
        self.assertTrue(data["ok"])
        result = data["result"]
        self.assertEqual(1, result["count"])
        self.assertTrue(result["results"][0]["ok"])

        status, data = self.client.json("POST", "/api/ops/batch", {"items": []})
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])

        status, data = self.client.json("POST", "/api/ops/batch", {"items": "bad"})
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])

        status, data = self.client.json("GET", "/api/ops/history?limit=bad")
        self.assertEqual(400, status, msg=data)
        self.assertFalse(data["ok"])

        status, data = self.client.json("GET", "/api/ops/history")
        self.assertEqual(200, status, msg=data)
        self.assertGreaterEqual(len(data["history"]), 1)


if __name__ == "__main__":
    unittest.main()
