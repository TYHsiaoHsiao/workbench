"""流程执行引擎：拓扑顺序执行节点，支持 dry-run、人工确认断点与恢复。

执行结果单向写回项目 state.json（state 为唯一事实来源），运行记录写入
`00_project/workflows/runs/<run_id>.json` 供审计与失败恢复。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core_router.project import load_state

from . import store
from .graph import FlowError, Graph, order_for_mode, validate_graph
from .nodes import NodeContext, NodeError, NodeResult, get_executor
from .registry import NodeTypeRegistry, load_node_types

EventSink = Callable[[dict[str, Any]], None]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _state_snapshot(project_root: Path) -> dict[str, Any]:
    try:
        return load_state(project_root)
    except Exception:  # noqa: BLE001 - 项目缺失时快照为空，由节点报错
        return {}


class Runner:
    """一次性运行会话：run() 启动，resume() 在确认断点后继续。"""

    def __init__(
        self,
        project_root: Path | str,
        graph_data: dict[str, Any],
        node_types: NodeTypeRegistry | None = None,
        dry_run: bool | None = None,
        auto_confirm: bool = False,
        event_sink: EventSink | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.graph_data = dict(graph_data)
        self.graph = Graph.from_dict(graph_data)
        self.node_types = node_types or load_node_types()
        self.validation = validate_graph(self.graph_data, self.node_types)
        self.dry_run = bool(
            self.graph.settings.get("dry_run_first", True) if dry_run is None else dry_run
        )
        self.auto_confirm = auto_confirm
        self.event_sink = event_sink
        self.events: list[dict[str, Any]] = []
        self.order: list[str] = []
        self.cursor = 0
        self.waiting_index: int | None = None
        self.session_active = False
        self.record: dict[str, Any] = {}

    # -- 公共入口 -----------------------------------------------------
    def run(self, mode: str = "full", target: str | None = None) -> dict[str, Any]:
        if not self.validation["ok"]:
            raise FlowError("流程图校验失败: " + "; ".join(self.validation["errors"]))
        self.order = order_for_mode(self.graph, mode=mode, target=target)
        self.cursor = 0
        self.session_active = True
        self.record = {
            "contract_version": "0.1",
            "run_id": store.new_run_id(),
            "graph_id": self.graph.graph_id,
            "project": self.graph.project or self.project_root.name,
            "status": "running",
            "mode": mode,
            "dry_run": self.dry_run,
            "started_at": _now(),
            "steps": [],
            "confirmations": [],
            "state_snapshot_before": _state_snapshot(self.project_root),
        }
        if mode != "full":
            self.record["target_node"] = target
        self._emit("run_started", {"run_id": self.record["run_id"], "order": self.order})
        self._continue()
        return self.result()

    def resume(self, approved: bool = True, note: str = "") -> dict[str, Any]:
        if self.waiting_index is None:
            raise FlowError("当前没有等待确认的节点")
        step = self.record["steps"][self.waiting_index]
        self.record.setdefault("confirmations", []).append(
            {
                "node_id": step["node_id"],
                "approved": bool(approved),
                "at": _now(),
                "note": note,
            }
        )
        if not approved:
            step["status"] = "skipped"
            step["logs"] = list(step.get("logs") or []) + ["人工取消确认，流程停止"]
            self._finish("canceled")
            return self.result()
        step["status"] = "succeeded"
        step["ended_at"] = _now()
        step["state_after"] = _state_snapshot(self.project_root)
        self.waiting_index = None
        self.cursor += 1
        self._emit("confirm_resumed", {"node_id": step["node_id"]})
        self._continue()
        return self.result()

    def result(self) -> dict[str, Any]:
        data: dict[str, Any] = {"ok": True, "run": self.record, "events": list(self.events)}
        if self.session_active and self.record.get("status") == "awaiting_confirm":
            data["awaiting"] = self._awaiting_payload()
        return data

    # -- 内部执行 -----------------------------------------------------
    def _continue(self) -> None:
        context = NodeContext(
            project_root=self.project_root,
            node_types=self.node_types,
            graph=self.graph,
            dry_run=self.dry_run,
        )
        while self.cursor < len(self.order):
            node_id = self.order[self.cursor]
            node = self.graph.node(node_id)
            before = _state_snapshot(self.project_root)
            step: dict[str, Any] = {
                "node_id": node_id,
                "status": "running",
                "started_at": _now(),
                "state_before": {"stage": before.get("stage"), "version": before.get("version")},
                "outputs": [],
                "logs": [],
            }
            self.record["steps"].append(step)
            self._save()
            self._emit("node_started", {"node_id": node_id, "label": node.label})

            if node.disabled:
                step.update(status="skipped", ended_at=_now(), logs=["节点已禁用，跳过"])
                self._emit("node_skipped", {"node_id": node_id})
                self.cursor += 1
                self._save()
                continue

            try:
                result = get_executor(node.type)(node, context)
            except (NodeError, FlowError) as exc:
                self._fail(step, str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - 引擎兜底，记录后中止
                self._fail(step, f"{type(exc).__name__}: {exc}")
                return

            step["outputs"] = list(result.outputs)
            step["logs"] = list(result.logs)
            if result.error:
                self._fail(step, result.error)
                return
            if result.status == "waiting_confirmation":
                if self.auto_confirm:
                    self.record.setdefault("confirmations", []).append(
                        {"node_id": node_id, "approved": True, "at": _now(), "note": "auto_confirm"}
                    )
                    step["logs"] = list(step["logs"]) + ["auto_confirm 自动确认"]
                else:
                    step["status"] = "waiting_confirmation"
                    step["ended_at"] = _now()
                    step["state_after"] = _state_snapshot(self.project_root)
                    self.waiting_index = len(self.record["steps"]) - 1
                    self.record["status"] = "awaiting_confirm"
                    self.record["summary"] = self._summary()
                    self._save()
                    self._emit(
                        "awaiting_confirm",
                        {
                            "node_id": node_id,
                            "prompt": result.prompt,
                            "detail_path": result.detail_path,
                        },
                    )
                    return
            step["status"] = "planned" if self.dry_run else "succeeded"
            step["ended_at"] = _now()
            step["state_after"] = _state_snapshot(self.project_root)
            self.cursor += 1
            self._save()
            self._emit(
                "node_finished",
                {"node_id": node_id, "status": step["status"], "outputs": step["outputs"]},
            )
        self._finish("succeeded")

    def _fail(self, step: dict[str, Any], message: str) -> None:
        step["status"] = "failed"
        step["ended_at"] = _now()
        step["error"] = message
        step["state_after"] = _state_snapshot(self.project_root)
        self._finish("failed")
        self._emit("run_failed", {"node_id": step["node_id"], "error": message})

    def _finish(self, status: str) -> None:
        self.record["status"] = status
        self.record["finished_at"] = _now()
        self.record["summary"] = self._summary()
        self.session_active = False
        self._save()
        self._emit("run_finished", {"status": status})

    def _summary(self) -> dict[str, Any]:
        steps = self.record.get("steps") or []
        return {
            "nodes": len(self.order),
            "executed": sum(1 for step in steps if step.get("status") in {"succeeded", "planned"}),
            "failed": sum(1 for step in steps if step.get("status") == "failed"),
            "waiting": sum(1 for step in steps if step.get("status") == "waiting_confirmation"),
            "dry_run": self.dry_run,
        }

    def _awaiting_payload(self) -> dict[str, Any]:
        if self.waiting_index is None:
            return {}
        step = self.record["steps"][self.waiting_index]
        node = self.graph.node(step["node_id"])
        return {
            "node_id": step["node_id"],
            "prompt": str(node.params.get("prompt") or "请确认后继续"),
            "detail_path": str(node.params.get("detail_path") or ""),
            "run_id": self.record["run_id"],
        }

    def _save(self) -> None:
        try:
            store.write_run(self.project_root, self.record)
        except (OSError, FlowError):
            pass

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        event = {"kind": kind, "at": _now(), **payload}
        self.events.append(event)
        if self.event_sink is not None:
            try:
                self.event_sink(event)
            except Exception:  # noqa: BLE001 - 事件推送失败不影响执行
                pass


def run_flow(
    project_root: Path | str,
    graph_data: dict[str, Any],
    mode: str = "full",
    target: str | None = None,
    dry_run: bool | None = None,
    auto_confirm: bool = False,
    node_types: NodeTypeRegistry | None = None,
) -> dict[str, Any]:
    runner = Runner(
        project_root,
        graph_data,
        node_types=node_types,
        dry_run=dry_run,
        auto_confirm=auto_confirm,
    )
    return runner.run(mode=mode, target=target)


def dump_run(run: dict[str, Any]) -> str:
    return json.dumps(run, ensure_ascii=False, indent=2)


def recover_run(
    project_root: str | Path,
    run_id: str,
    restore_state: bool = False,
    auto_confirm: bool = True,
) -> dict[str, Any]:
    """从历史运行恢复：可选回滚运行前状态快照，然后按当前项目状态重跑同一流程图。"""
    project = Path(project_root)
    original = store.read_run(project, run_id)
    state_restored = False
    if restore_state:
        snapshot = original.get("state_snapshot_before")
        if isinstance(snapshot, dict) and snapshot:
            from core_router.project import load_state, refresh_status_card, save_state

            current = load_state(project)
            history = project / "00_project" / "history"
            history.mkdir(parents=True, exist_ok=True)
            backup = history / f"state-before-recover-{_now().replace(':', '')}.json"
            backup.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            save_state(project, snapshot)
            refresh_status_card(project)
            state_restored = True
    graph_id = original.get("graph_id") or ""
    graph = store.read_graph_data(project, graph_id)
    runner = Runner(project, graph, dry_run=False, auto_confirm=auto_confirm)
    result = runner.run(mode=original.get("mode") or "full", target=original.get("target_node"))
    record = result["run"]
    record["recovered_from"] = run_id
    record["state_restored"] = state_restored
    store.write_run(project, record)
    result["run"] = record
    result["recovered_from"] = run_id
    result["state_restored"] = state_restored
    return result
