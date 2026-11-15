"""节点执行器（M1：start / stage / confirm / end）。

每个执行器只调用既有内核服务，不重复实现业务逻辑；执行结果由 runner 统一写回运行记录。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core_router.gates import advance, ensure_stage_gates, pass_gate, pending_gates
from core_router.project import load_state, refresh_status_card, save_state
from core_router.registry import load_registry

from .graph import Graph, Node
from .registry import NodeTypeRegistry


class NodeError(Exception):
    """节点执行失败（由 runner 包装为运行失败步骤）。"""


@dataclass
class NodeContext:
    project_root: Path
    node_types: NodeTypeRegistry
    graph: Graph | None = None
    dry_run: bool = True
    _stage_registry: Any = field(default=None, repr=False)

    def stage_registry(self) -> Any:
        if self._stage_registry is None:
            self._stage_registry = load_registry()
        return self._stage_registry


@dataclass
class NodeResult:
    status: str = "succeeded"  # succeeded | waiting_confirmation | planned
    outputs: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    prompt: str = ""
    detail_path: str = ""


Executor = Callable[[Node, NodeContext], NodeResult]


def _exec_start(node: Node, ctx: NodeContext) -> NodeResult:
    state = load_state(ctx.project_root)
    project = state.get("project")
    entry = state.get("entry")
    params_entry = node.params.get("entry")
    logs = [f"绑定项目 {project}（入口 {entry}，当前阶段 {state.get('stage')}）"]
    if params_entry and params_entry != entry:
        logs.append(f"节点入口 {params_entry} 与项目入口 {entry} 不一致（以项目为准）")
    return NodeResult(outputs=[f"项目已绑定：{project}"], logs=logs)


def _exec_stage(node: Node, ctx: NodeContext) -> NodeResult:
    stage = str(node.params.get("stage") or "")
    auto_gates = bool(node.params.get("auto_gates", True))
    state = load_state(ctx.project_root)
    current = str(state.get("stage") or "")
    if current != stage:
        raise NodeError(
            f"当前阶段 {current} 与节点阶段 {stage} 不一致；请先运行前置阶段节点或检查项目状态"
        )

    registry = ctx.stage_registry()
    pending = pending_gates(state, stage, registry=registry)
    logs: list[str] = []
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 阶段 {stage}：将通过 {len(pending)} 道门禁并 advance 到下一阶段"],
            logs=[f"待处理门禁: {', '.join(pending) if pending else '无'}"],
        )

    if auto_gates:
        for gate_id in list(pending):
            pass_gate(state, gate_id, note="流程图自动通过（auto_gates）", registry=registry)
        logs.append(f"已自动通过门禁: {', '.join(pending) if pending else '无'}")
    ensure_stage_gates(state, stage, registry=registry)
    pending = pending_gates(state, stage, registry=registry)
    if pending:
        save_state(ctx.project_root, state)
        refresh_status_card(ctx.project_root)
        raise NodeError("门禁未通过，不能推进: " + ", ".join(pending))

    next_stage = advance(state, registry=registry)
    save_state(ctx.project_root, state)
    refresh_status_card(ctx.project_root)
    logs.append(f"已推进到阶段 {next_stage}")
    return NodeResult(outputs=[f"阶段 {stage} 完成 → {next_stage}"], logs=logs)


def _exec_confirm(node: Node, ctx: NodeContext) -> NodeResult:
    prompt = str(node.params.get("prompt") or "请确认后继续")
    detail_path = str(node.params.get("detail_path") or "")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将在此暂停等待人工确认：{prompt}"],
            logs=["dry-run 不产生确认请求"],
        )
    return NodeResult(status="waiting_confirmation", prompt=prompt, detail_path=detail_path)


def _exec_end(node: Node, ctx: NodeContext) -> NodeResult:
    state = load_state(ctx.project_root)
    return NodeResult(
        outputs=[f"流程结束（项目阶段 {state.get('stage')}，状态版本 {state.get('version')}）"]
    )


EXECUTORS: dict[str, Executor] = {
    "start": _exec_start,
    "stage": _exec_stage,
    "confirm": _exec_confirm,
    "end": _exec_end,
}


def get_executor(node_type: str) -> Executor:
    executor = EXECUTORS.get(node_type)
    if executor is None:
        raise NodeError(f"节点类型 {node_type} 的 M1 执行器未实现")
    return executor
