"""本地可视化工作台 Web 服务（Python 标准库，零第三方依赖）。

启动:
    workbench.py flow serve --project <项目名或路径>

安全边界:
- 默认只监听 127.0.0.1。
- 默认启用访问令牌（首次启动打印带 token 的 URL）。
- 写操作仅允许项目目录内的流程图与运行记录，不提供任意文件读写。
"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from core_router.project import load_state
from flow import (
    FlowError,
    Runner,
    build_replay,
    compare_runs,
    default_graph,
    instantiate_template,
    list_graphs,
    list_runs,
    load_node_types,
    load_templates,
    read_graph_data,
    read_run,
    recover_run,
    resolve_project,
    validate_graph,
    write_graph_data,
)
from flow.store import graph_id_from_name

STATIC_DIR = Path(__file__).resolve().parent / "static"
WORKBENCH_ROOT = Path(__file__).resolve().parents[2]

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _workbench_version() -> str:
    path = WORKBENCH_ROOT / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _list_projects() -> list[dict[str, Any]]:
    """扫描默认项目根与仓库同级 projects 目录。"""
    roots: list[Path] = []
    try:
        from core_router.project import default_projects_root

        roots.append(Path(default_projects_root()))
    except Exception:  # pragma: no cover - 环境异常时降级
        pass
    roots.append(WORKBENCH_ROOT.parent / "projects")
    found: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or not (child / "00_project" / "state.json").is_file():
                continue
            entry: dict[str, Any] = {
                "name": child.name,
                "path": str(child),
                "stage": "?",
                "version": "?",
            }
            try:
                state = json.loads((child / "00_project" / "state.json").read_text(encoding="utf-8"))
                entry["project"] = state.get("project") or child.name
                entry["stage"] = state.get("stage", "?")
                entry["version"] = state.get("version", "?")
                entry["entry"] = state.get("entry", "?")
                entry["updated_at"] = state.get("revision_log", [{}])[-1].get("at", "") if state.get("revision_log") else ""
                entry["artifacts"] = len(state.get("stage_artifacts") or {})
                entry["pending_gates"] = sum(
                    1
                    for gate in (state.get("gates") or [])
                    if isinstance(gate, dict) and gate.get("status") == "pending"
                )
                try:
                    entry["workflows"] = len(list_graphs(child))
                except Exception:  # noqa: BLE001 - 统计失败不影响列表
                    entry["workflows"] = 0
                try:
                    run_rows = list_runs(child, limit=20)
                except Exception:  # noqa: BLE001
                    run_rows = []
                entry["runs"] = len(run_rows)
                entry["last_run"] = (
                    {
                        "status": run_rows[0].get("status"),
                        "at": run_rows[0].get("started_at") or run_rows[0].get("finished_at") or "",
                    }
                    if run_rows
                    else None
                )
            except (OSError, json.JSONDecodeError):
                pass
            found.setdefault(str(child), entry)
    return list(found.values())


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], project_root: Path, token: str | None) -> None:
        super().__init__(address, WorkbenchHandler)
        self.project_root = Path(project_root)
        self.token = token
        self.sessions: dict[str, Runner] = {}


class WorkbenchHandler(BaseHTTPRequestHandler):
    server: WorkbenchServer

    # ---------------- 基础输出 ----------------
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - 标准库签名
        if getattr(self, "quiet", False):
            return
        print(f"[webui] {self.address_string()} {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(status, body, CONTENT_TYPES[".json"])

    def _error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"ok": False, "error": message}, status)

    # ---------------- 鉴权 ----------------
    def _token_ok(self, query: dict[str, list[str]]) -> bool:
        expected = self.server.token
        if not expected:
            return True
        given = (query.get("token") or [None])[0] or self.headers.get("X-Workbench-Token")
        return given == expected

    # ---------------- 请求体 ----------------
    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 8 * 1024 * 1024:
            raise FlowError("请求体过大（>8MB）")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FlowError(f"请求体不是合法 JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise FlowError("请求体必须是 JSON 对象")
        return data

    def _query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query)

    def _project_from(self, query: dict[str, list[str]]) -> Path:
        ref = (query.get("project") or [None])[0] or str(self.server.project_root)
        return resolve_project(ref)

    # ---------------- 静态文件 ----------------
    def _serve_static(self, name: str) -> None:
        relative = "index.html" if name in {"", "/"} else unquote(name.lstrip("/"))
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
            self._send(HTTPStatus.NOT_FOUND, b"not found", CONTENT_TYPES[".html"])
            return
        if not target.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"not found", CONTENT_TYPES[".html"])
            return
        content_type = CONTENT_TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, target.read_bytes(), content_type)

    # ---------------- 路由 ----------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                if not self._token_ok(query):
                    self._error("访问令牌无效", HTTPStatus.UNAUTHORIZED)
                    return
                self._api_get(path, query)
            else:
                self._serve_static(path)
        except FlowError as exc:
            self._error(str(exc))
        except Exception as exc:  # pragma: no cover - 防御性兜底
            self._error(f"服务器内部错误: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        query = self._query()
        try:
            if not path.startswith("/api/"):
                self._error("not found", HTTPStatus.NOT_FOUND)
                return
            if not self._token_ok(query):
                self._error("访问令牌无效", HTTPStatus.UNAUTHORIZED)
                return
            body = self._read_json()
            if path.startswith("/api/workflows/"):
                graph_id = unquote(path[len("/api/workflows/"):]).strip("/")
                project = self._project_from(query)
                graph = body.get("graph") or body
                if graph.get("graph_id") and graph["graph_id"] != graph_id:
                    raise FlowError("graph_id 与 URL 不一致")
                graph["graph_id"] = graph_id
                result = validate_graph(graph, load_node_types())
                if not result["ok"]:
                    self._json({"ok": False, "errors": result["errors"], "warnings": result["warnings"]}, HTTPStatus.UNPROCESSABLE_ENTITY)
                    return
                write_graph_data(project, graph)
                self._json({"ok": True, "warnings": result["warnings"], "graph": graph})
                return
            self._error("not found", HTTPStatus.NOT_FOUND)
        except FlowError as exc:
            self._error(str(exc))
        except Exception as exc:  # pragma: no cover
            self._error(f"服务器内部错误: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        query = self._query()
        try:
            if not path.startswith("/api/"):
                self._error("not found", HTTPStatus.NOT_FOUND)
                return
            if not self._token_ok(query):
                self._error("访问令牌无效", HTTPStatus.UNAUTHORIZED)
                return
            body = self._read_json()
            self._api_post(path, query, body)
        except FlowError as exc:
            self._error(str(exc))
        except Exception as exc:  # pragma: no cover
            self._error(f"服务器内部错误: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    # ---------------- API 实现 ----------------
    def _api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/workbench":
            project = self._project_from(query)
            self._json(
                {
                    "ok": True,
                    "project": str(project),
                    "project_name": project.name,
                    "version": _workbench_version(),
                    "graphs": len(list_graphs(project)),
                }
            )
            return
        if path == "/api/projects":
            self._json({"ok": True, "projects": _list_projects()})
            return
        if path.startswith("/api/projects/") and path.endswith("/summary"):
            name = unquote(path[len("/api/projects/"): -len("/summary")]).strip("/")
            project = resolve_project(name)
            state = load_state(project)
            artifacts = []
            for stage, summary in (state.get("stage_artifacts") or {}).items():
                files = []
                for token in re.findall(
                    r"[0-9A-Za-z_\u4e00-\u9fff./\-]+\.(?:md|json|txt)", str(summary)
                ):
                    file_path = project / token
                    if file_path.exists():
                        files.append(
                            {
                                "path": token,
                                "size": file_path.stat().st_size,
                                "modified_at": file_path.stat().st_mtime,
                            }
                        )
                artifacts.append({"stage": stage, "summary": summary, "files": files})
            graphs = []
            for item in list_graphs(project):
                try:
                    graph = read_graph_data(project, item["graph_id"])
                except FlowError:
                    continue
                graphs.append(
                    {
                        "graph_id": item["graph_id"],
                        "name": graph.get("name"),
                        "nodes": [
                            {
                                "id": node.get("id"),
                                "type": node.get("type"),
                                "label": node.get("label"),
                                "x": (node.get("position") or {}).get("x"),
                                "y": (node.get("position") or {}).get("y"),
                            }
                            for node in graph.get("nodes") or []
                        ],
                        "edges": [
                            {"from": edge.get("from"), "to": edge.get("to")}
                            for edge in graph.get("edges") or []
                        ],
                    }
                )
            runs = list_runs(project, limit=20)
            self._json(
                {
                    "ok": True,
                    "project": project.name,
                    "path": str(project),
                    "stage": state.get("stage"),
                    "version": state.get("version"),
                    "entry": state.get("entry"),
                    "artifacts": artifacts,
                    "graphs": graphs,
                    "runs": len(runs),
                    "latest_runs": runs[:5],
                }
            )
            return
        if path == "/api/node-types":
            registry = load_node_types()
            self._json({"ok": True, **registry.to_dict()})
            return
        if path == "/api/templates":
            self._json({"ok": True, "templates": load_templates()})
            return
        if path == "/api/workflows":
            project = self._project_from(query)
            self._json({"ok": True, "project": str(project), "graphs": list_graphs(project)})
            return
        if path == "/api/runs":
            project = self._project_from(query)
            limit = 30
            values = query.get("limit") or []
            if values:
                try:
                    limit = max(1, min(200, int(values[0])))
                except ValueError:
                    pass
            self._json({"ok": True, "project": str(project), "runs": list_runs(project, limit=limit)})
            return
        if path.startswith("/api/workflows/"):
            project = self._project_from(query)
            graph_id = unquote(path[len("/api/workflows/"):]).strip("/")
            self._json({"ok": True, "project": str(project), "graph": read_graph_data(project, graph_id)})
            return
        if path.startswith("/api/runs/") and path.endswith("/diff"):
            project = self._project_from(query)
            run_id = unquote(path[len("/api/runs/"): -len("/diff")]).strip("/")
            target = read_run(project, run_id)
            others = query.get("other") or []
            if others:
                other_id = others[0]
            else:
                candidates = [
                    item["run_id"]
                    for item in list_runs(project, limit=50)
                    if item.get("run_id") != run_id
                ]
                other_id = candidates[0] if candidates else ""
            if not other_id:
                raise FlowError("没有可对比的另一次运行")
            base = read_run(project, other_id)
            self._json(
                {"ok": True, "project": str(project), "diff": compare_runs(base, target)}
            )
            return
        if path.startswith("/api/runs/") and path.endswith("/replay"):
            project = self._project_from(query)
            run_id = unquote(path[len("/api/runs/"): -len("/replay")]).strip("/")
            run = read_run(project, run_id)
            graph = None
            graph_id = str(run.get("graph_id") or "")
            if graph_id:
                try:
                    graph = read_graph_data(project, graph_id)
                except FlowError:
                    graph = None
            self._json({"ok": True, "project": str(project), "replay": build_replay(run, graph)})
            return
        if path.startswith("/api/runs/"):
            project = self._project_from(query)
            run_id = unquote(path[len("/api/runs/"):]).strip("/")
            self._json({"ok": True, "run": read_run(project, run_id)})
            return
        self._error("not found", HTTPStatus.NOT_FOUND)

    def _api_post(self, path: str, query: dict[str, list[str]], body: dict[str, Any]) -> None:
        if path == "/api/workflows/new":
            project = self._project_from(query) if query.get("project") else resolve_project(body.get("project") or str(self.server.project_root))
            name = str(body.get("name") or "").strip()
            if not name:
                raise FlowError("缺少流程图名称 name")
            graph_id = str(body.get("graph_id") or "").strip() or graph_id_from_name(name)
            template_id = str(body.get("template_id") or "").strip()
            if template_id:
                data = instantiate_template(template_id, project.name, graph_id=graph_id, name=name)
            else:
                data = default_graph(project.name, graph_id=graph_id)
                data["name"] = name
                data["nodes"][0]["params"]["project"] = project.name
            write_graph_data(project, data)
            self._json({"ok": True, "graph_id": graph_id, "graph": data})
            return
        if path == "/api/workflows/import":
            project = resolve_project(body.get("project") or str(self.server.project_root))
            graph = body.get("graph") or {}
            if not isinstance(graph, dict):
                raise FlowError("graph 必须是流程图 JSON 对象")
            result = validate_graph(graph, load_node_types())
            if not result["ok"]:
                self._json({"ok": False, **result}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            graph_id = str(body.get("graph_id") or graph.get("graph_id") or "").strip()
            if not graph_id:
                raise FlowError("缺少 graph_id")
            graph = dict(graph)
            graph["graph_id"] = graph_id
            graph["project"] = project.name
            graph["name"] = str(graph.get("name") or graph_id)
            write_graph_data(project, graph)
            self._json({"ok": True, "project": str(project), "graph_id": graph_id, "graph": graph})
            return
        if path == "/api/workflows/validate":
            graph = body.get("graph") or body
            result = validate_graph(graph, load_node_types())
            self._json({"ok": result["ok"], **result})
            return
        if path == "/api/runs":
            project = resolve_project(body.get("project") or str(self.server.project_root))
            graph_id = str(body.get("graph_id") or "").strip()
            if not graph_id:
                raise FlowError("缺少 graph_id")
            graph = read_graph_data(project, graph_id)
            runner = Runner(
                project,
                graph,
                dry_run=body.get("dry_run"),
                auto_confirm=bool(body.get("auto_confirm")),
            )
            result = runner.run(
                mode=str(body.get("mode") or "full"),
                target=body.get("target_node") or None,
            )
            self.server.sessions[result["run"]["run_id"]] = runner
            self._json(result)
            return
        if path == "/api/runs/batch":
            project = resolve_project(body.get("project") or str(self.server.project_root))
            graph_ids = body.get("graph_ids") or []
            if not graph_ids:
                graph_ids = [item["graph_id"] for item in list_graphs(project)]
            dry_run = body.get("dry_run")
            auto_confirm = bool(body.get("auto_confirm", True))
            results = []
            for graph_id in graph_ids:
                try:
                    graph = read_graph_data(project, str(graph_id))
                    runner = Runner(project, graph, dry_run=dry_run, auto_confirm=auto_confirm)
                    run_result = runner.run(mode="full")
                    run = run_result["run"]
                    self.server.sessions[run["run_id"]] = runner
                    results.append(
                        {
                            "graph_id": graph_id,
                            "ok": run.get("status") in {"succeeded", "awaiting_confirm"},
                            "status": run.get("status"),
                            "run_id": run.get("run_id"),
                            "steps": len(run.get("steps") or []),
                        }
                    )
                except FlowError as exc:
                    results.append({"graph_id": graph_id, "ok": False, "status": "error", "error": str(exc)})
            self._json(
                {
                    "ok": all(item.get("ok") for item in results),
                    "project": str(project),
                    "count": len(results),
                    "results": results,
                }
            )
            return
        if path.startswith("/api/runs/") and path.endswith("/recover"):
            run_id = unquote(path[len("/api/runs/"): -len("/recover")]).strip("/")
            project = resolve_project(body.get("project") or str(self.server.project_root))
            result = recover_run(
                project,
                run_id,
                restore_state=bool(body.get("restore_state")),
                auto_confirm=bool(body.get("auto_confirm", True)),
            )
            self._json(result)
            return
        if path.startswith("/api/runs/") and path.endswith("/confirm"):
            run_id = unquote(path[len("/api/runs/"): -len("/confirm")]).strip("/")
            runner = self.server.sessions.get(run_id)
            if runner is None:
                self._error("确认会话已失效（服务可能重启过），请在运行面板重新执行。", HTTPStatus.CONFLICT)
                return
            result = runner.resume(approved=bool(body.get("approved", True)), note=str(body.get("note") or ""))
            self._json(result)
            return
        self._error("not found", HTTPStatus.NOT_FOUND)


def create_server(
    project_root: Path | str,
    host: str = "127.0.0.1",
    port: int = 0,
    use_token: bool = True,
) -> WorkbenchServer:
    """创建（但不启动）Web 服务；port=0 时由系统分配。"""
    project = resolve_project(project_root)
    token = secrets.token_urlsafe(12) if use_token else None
    server = WorkbenchServer((host, port), project, token)
    return server


def serve_forever(
    project_root: Path | str,
    host: str = "127.0.0.1",
    port: int = 8899,
    use_token: bool = True,
) -> None:
    server = create_server(project_root, host=host, port=port, use_token=use_token)
    actual_host, actual_port = server.server_address[:2]
    token = server.token
    shown_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{shown_host}:{actual_port}/"
    if token:
        url += f"?token={token}"
    print("可视化工作台已启动（仅本机访问）")
    print(f"项目: {server.project_root}")
    print(f"打开: {url}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已收到中断，正在停止服务…")
    finally:
        server.server_close()
        print("服务已停止。")
