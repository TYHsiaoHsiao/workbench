"""节点执行器（M2：start / stage / knowledge_search / style_apply / style_inject /
artifact_register / check_content / confirm / export / end）。

每个执行器只调用既有内核服务，不重复实现业务逻辑；执行结果由 runner 统一写回运行记录。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core_router.check import content_checks
from core_router.gates import advance, ensure_stage_gates, pass_gate, pending_gates
from core_router.project import (
    export_project,
    load_state,
    refresh_status_card,
    register_artifacts,
    save_state,
)
from core_router.registry import load_registry

from .graph import STAGE_ORDER, Graph, Node
from .locks import LockError, log_transaction, state_lock
from .registry import NodeTypeRegistry


class NodeError(Exception):
    """节点执行失败（由 runner 包装为运行失败步骤）。"""


@dataclass
class NodeContext:
    project_root: Path
    node_types: NodeTypeRegistry
    graph: Graph | None = None
    dry_run: bool = True
    run_id: str = ""
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
    selected_ports: list[str] | None = None  # M7：条件节点选中的分支端口；None=全部端口有效


Executor = Callable[[Node, NodeContext], NodeResult]


def _locked_mutation(
    ctx: NodeContext,
    node: Node,
    stage: str,
    mutations: list[str],
    action: Callable[[], Any],
) -> Any:
    """在项目状态锁内执行写操作，并记录事务日志（M6）。

    state.json 是唯一事实来源：写状态的节点（知识卡/风格卡/产物等）即使被并行波次调度，
    也通过文件锁串行化，避免并发覆盖。
    """
    try:
        with state_lock(ctx.project_root):
            result = action()
            log_transaction(
                ctx.project_root,
                {
                    "action": node.type,
                    "node_id": node.id,
                    "stage": stage,
                    "mutations": mutations,
                    "run_id": ctx.run_id,
                    "ok": True,
                },
            )
            return result
    except LockError as exc:
        raise NodeError(f"状态锁失败: {exc}") from exc


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


def _exec_knowledge_search(node: Node, ctx: NodeContext) -> NodeResult:
    params = node.params
    stage = str(params.get("stage") or "")
    problem = str(params.get("problem") or "")
    queries = params.get("queries") or []
    if not stage or not problem or not queries:
        raise NodeError("知识检索节点缺少 stage / problem / queries 参数")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 阶段 {stage} 知识检索：{len(queries)} 个查询（不会写知识卡）"],
            logs=["dry-run 不调用知识服务，不写卡片"],
        )
    from knowledge_service import KnowledgeService, KnowledgeServiceError

    kb_root = params.get("kb_root") or None
    try:
        service = KnowledgeService(kb_root=kb_root) if kb_root else KnowledgeService()
        result = service.search(
            project=str(load_state(ctx.project_root).get("project") or ctx.project_root.name),
            stage=stage,
            problem=problem,
            queries=[str(item) for item in queries],
            candidates_limit=int(params.get("candidates_limit", 40)),
            evidence_limit=int(params.get("evidence_limit", 8)),
            fallback=bool(params.get("fallback", True)),
        )
    except KnowledgeServiceError as exc:
        raise NodeError(f"知识检索失败: {exc}") from exc

    card = result.get("card") if isinstance(result, dict) else None
    if card is None and isinstance(result, dict) and "card_id" in result:
        card = result
    if card is None:
        raise NodeError("知识服务未返回知识卡")
    def _write_card() -> str:
        card_dir = ctx.project_root / "00_project" / "knowledge-cards"
        card_dir.mkdir(parents=True, exist_ok=True)
        card_path = card_dir / f"{stage}-candidates.json"
        card_path.write_text(
            json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rel_path = card_path.relative_to(ctx.project_root).as_posix()

        current = load_state(ctx.project_root)
        bridge_state = dict(current.get("knowledge_bridge") or {})
        if bridge_state.get("status", "off") == "off":
            bridge_state["status"] = "requested"
        bridge_state["last_card"] = rel_path
        current["knowledge_bridge"] = bridge_state
        save_state(ctx.project_root, current)
        refresh_status_card(ctx.project_root)
        return rel_path

    rel = _locked_mutation(
        ctx, node, stage, ["knowledge_cards", "knowledge_bridge"], _write_card
    )
    state = load_state(ctx.project_root)
    bridge = dict(state.get("knowledge_bridge") or {})

    candidates = card.get("candidates") or []
    evidence = card.get("evidence") or []
    status = card.get("status") or (result.get("status") if isinstance(result, dict) else "") or "unknown"
    return NodeResult(
        outputs=[f"知识卡: {rel}（状态 {status}，候选 {len(candidates)}，证据 {len(evidence)}）"],
        logs=[f"知识桥状态 → {bridge.get('status')}"],
    )


def _exec_style_apply(node: Node, ctx: NodeContext) -> NodeResult:
    style = str(node.params.get("style") or "")
    if not style:
        raise NodeError("风格卡节点缺少 style 参数")
    tool = node.params.get("tool") or None
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将应用风格 {style}" + (f"（工具 {tool}）" if tool else "")],
            logs=["dry-run 不写风格卡"],
        )
    from style_service import StyleService, StyleServiceError

    try:
        result = _locked_mutation(
            ctx, node, "", ["style_profile"], lambda: StyleService().apply(ctx.project_root, style, tool)
        )
    except StyleServiceError as exc:
        raise NodeError(f"风格应用失败: {exc}") from exc
    path = result.get("profile") or result.get("profile_path") or result.get("path")
    return NodeResult(
        outputs=[f"风格卡已应用：{path or '00_project/style-cards/'}"],
        logs=[f"风格 {style}" + (f" · 工具 {tool}" if tool else "")],
    )


def _exec_style_inject(node: Node, ctx: NodeContext) -> NodeResult:
    stage = str(node.params.get("stage") or "")
    tool = str(node.params.get("tool") or "")
    items = node.params.get("items") or []
    if not stage or not tool or not items:
        raise NodeError("风格注入节点缺少 stage / tool / items 参数")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将向 {stage}/{tool} 注入 {len(items)} 条提示词"],
            logs=["dry-run 不写注入记录"],
        )
    from style_service import StyleService, StyleServiceError

    try:
        result = _locked_mutation(
            ctx,
            node,
            stage,
            ["style_injection"],
            lambda: StyleService().inject_batch(
                ctx.project_root,
                stage,
                tool,
                list(items),
                per_shot_records=bool(node.params.get("per_shot", True)),
            ),
        )
    except StyleServiceError as exc:
        raise NodeError(f"风格注入失败: {exc}") from exc
    return NodeResult(
        outputs=[f"已注入 {result.get('count', len(items))} 条 → {result.get('record')}"],
        logs=[f"风格 {result.get('style_id')} · {stage}/{tool}"],
    )


def _exec_artifact_register(node: Node, ctx: NodeContext) -> NodeResult:
    stage = str(node.params.get("stage") or "")
    kind = str(node.params.get("kind") or "")
    paths = [str(item) for item in (node.params.get("paths") or [])]
    if not stage or not kind or not paths:
        raise NodeError("产物登记节点缺少 stage / kind / paths 参数")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将登记阶段 {stage} 的 {len(paths)} 个产物（kind={kind}）"],
            logs=["dry-run 不写 stage_artifacts"],
        )
    try:
        result = _locked_mutation(
            ctx,
            node,
            stage,
            ["stage_artifacts", "revision_log"],
            lambda: register_artifacts(
                ctx.project_root,
                stage,
                kind,
                paths,
                note=str(node.params.get("note") or "流程节点登记"),
            ),
        )
    except Exception as exc:  # ProjectError 等
        raise NodeError(f"产物登记失败: {exc}") from exc
    return NodeResult(
        outputs=[f"已登记：{result.get('summary') or str(result.get('files') and len(result['files']))}"],
        logs=[f"阶段 {stage} · {kind}"],
    )


def _exec_check_content(node: Node, ctx: NodeContext) -> NodeResult:
    state = load_state(ctx.project_root)
    errors, warnings = content_checks(ctx.project_root, state)
    logs = [f"[提示] {item}" for item in warnings]
    fail_on_error = bool(node.params.get("fail_on_error", True))
    if errors and fail_on_error:
        raise NodeError("内容检查失败: " + "；".join(errors))
    status = "succeeded" if not errors else "succeeded"
    outputs = [f"内容检查完成：{len(errors)} 个错误，{len(warnings)} 条提示"]
    if errors:
        outputs.append("（已忽略错误：fail_on_error=false）")
        logs.extend(f"[错误] {item}" for item in errors)
    return NodeResult(status=status, outputs=outputs, logs=logs)


def _exec_export(node: Node, ctx: NodeContext) -> NodeResult:
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=["[dry-run] 将导出项目 zip"],
            logs=["dry-run 不生成导出文件"],
        )
    try:
        result = export_project(ctx.project_root, node.params.get("out") or None)
    except Exception as exc:
        raise NodeError(f"导出失败: {exc}") from exc
    return NodeResult(
        outputs=[f"已导出：{result.get('archive')}（{result.get('files')} 个文件）"],
        logs=[f"大小 {result.get('bytes')} 字节"],
    )


def _exec_condition(node: Node, ctx: NodeContext) -> NodeResult:
    from .conditions import ConditionError, evaluate

    expression = str(node.params.get("when") or "always")
    state = load_state(ctx.project_root)
    try:
        matched = evaluate(expression, state, iteration=0)
    except ConditionError as exc:
        raise NodeError(f"条件求值失败: {exc}") from exc
    branch = "true" if matched else "false"
    label = "真" if matched else "假"
    logs = [f"条件「{expression}」→ {label}（分支端口 {branch}）"]
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 条件「{expression}」将走 {branch} 分支"],
            logs=logs,
            selected_ports=[branch],
        )
    return NodeResult(
        outputs=[f"条件「{expression}」→ {branch}（stage={state.get('stage')}）"],
        logs=logs,
        selected_ports=[branch],
    )


def _exec_loop(node: Node, ctx: NodeContext) -> NodeResult:
    """循环节点由 runner 内部展开执行；本执行器只覆盖 dry-run/兜底场景。"""
    max_iterations = int(node.params.get("max_iterations", 3) or 3)
    until = str(node.params.get("until") or "never")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 循环节点将最多迭代 {max_iterations} 次（until={until}），由引擎展开循环体"],
            logs=["dry-run 不执行循环体"],
            selected_ports=["done"],
        )
    raise NodeError("循环节点必须由执行引擎展开执行（当前上下文不支持直接执行）")


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




def _next_reference_id(entries: list[dict[str, Any]]) -> int:
    used: list[int] = []
    for entry in entries:
        match = re.fullmatch(r"参考方法([0-9]{3})", str(entry.get("id") or ""))
        if match:
            used.append(int(match.group(1)))
    return (max(used) + 1) if used else 1


def _project_rel(ctx: NodeContext, rel_path: str) -> tuple[Path, str]:
    root = Path(ctx.project_root).resolve()
    path = Path(rel_path)
    if not path.is_absolute():
        path = root / path
    try:
        path = path.resolve()
        relative = path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise NodeError(f"路径必须位于项目目录内：{rel_path}") from exc
    return path, relative.as_posix()


def _exec_knowledge_adopt(node: Node, ctx: NodeContext) -> NodeResult:
    """把已确认知识卡写入参考记忆（契约校验、编号、state.references 同步）。"""
    from contracts import validate as validate_contract
    from core_router.memory import load_memory, memory_path, scope_for_stage
    from core_router.project import now as project_now

    params = node.params
    max_entries = int(params.get("max_entries", 3))
    if max_entries < 1:
        raise NodeError("max_entries 必须 >= 1")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将采纳知识卡证据（最多 {max_entries} 条）"],
            logs=["dry-run 不写参考记忆"],
        )

    state = load_state(ctx.project_root)
    card_rel = str(params.get("card") or "")
    if not card_rel:
        card_rel = str((state.get("knowledge_bridge") or {}).get("last_card") or "")
    if not card_rel:
        raise NodeError("未找到知识卡：请指定 card 参数，或先运行知识检索节点")
    card_path, rel = _project_rel(ctx, card_rel)
    if not card_path.is_file():
        raise NodeError(f"知识卡不存在：{rel}")
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NodeError(f"知识卡不是合法 JSON：{exc}") from exc
    problems = validate_contract(card, schema_name="knowledge-card.schema.json")
    if problems:
        raise NodeError("知识卡不符合契约：" + "；".join(problems))
    confirmed = card.get("confirmed")
    if params.get("require_confirmed", True) and not (
        isinstance(confirmed, dict) and str(confirmed.get("by") or "").strip()
    ):
        raise NodeError("知识卡尚未确认（confirmed 为空），请先人工确认后再采纳")

    stage = str(card.get("stage") or "01")
    if stage not in STAGE_ORDER:
        raise NodeError(f"知识卡阶段非法：{stage}")
    scope_param = params.get("scope")
    scopes = [str(scope_param)] if scope_param else list(card.get("scope") or [scope_for_stage(stage)])

    def adopt() -> list[dict[str, Any]]:
        memory = load_memory(ctx.project_root)
        entries = list(memory.get("entries") or [])
        existing = {(str(e.get("local_path")), str(e.get("page_hits"))) for e in entries}
        added: list[dict[str, Any]] = []
        for evidence in list(card.get("evidence") or [])[:max_entries]:
            local_path = str(evidence.get("path") or "")
            page_hits = str(evidence.get("page") or "")
            if not local_path or not page_hits:
                continue
            if (local_path, page_hits) in existing:
                continue
            snippet = str(evidence.get("snippet") or "").strip()[:160]
            source = Path(local_path).stem or "知识卡"
            if local_path.startswith(("05-", "06-", "07-")):
                entry_type = "screenplay"
            elif local_path.startswith("08-"):
                entry_type = "method_book"
            else:
                entry_type = "other"
            stamp = project_now()
            entry = {
                "id": f"参考方法{_next_reference_id(entries):03d}",
                "status": "enabled",
                "source": source,
                "type": entry_type,
                "local_path": local_path,
                "page_hits": page_hits,
                "method": f"从《{source}》{page_hits}迁移：{snippet}",
                "scope": scopes,
                "stage": stage,
                "binding_facts": [
                    f"项目：{state.get('project')}",
                    f"知识卡：{card.get('card_id')}",
                ],
                "forbidden": ["照搬原剧情与人物关系", "直接复制对白"],
                "confirmed": {
                    "by": str((confirmed or {}).get("by") or "用户"),
                    "at": stamp,
                },
                "change_log": [
                    {
                        "at": stamp,
                        "action": "created",
                        "note": f"复合节点 knowledge_adopt 从知识卡 {card.get('card_id')} 采纳",
                    }
                ],
            }
            entries.append(entry)
            existing.add((local_path, page_hits))
            added.append(entry)
        if not added:
            return []
        memory["entries"] = entries
        problems = validate_contract(memory, schema_name="reference-memory.schema.json")
        if problems:
            raise NodeError("参考记忆校验失败：" + "；".join(problems))
        memory_path(ctx.project_root).write_text(
            json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        current = load_state(ctx.project_root)
        refs = list(current.get("references") or [])
        bridge = dict(current.get("knowledge_bridge") or {})
        confirmed_refs = list(bridge.get("confirmed_references") or [])
        for entry in added:
            if entry["id"] not in refs:
                refs.append(entry["id"])
            if entry["id"] not in confirmed_refs:
                confirmed_refs.append(entry["id"])
        current["references"] = refs
        bridge["status"] = "on"
        bridge["confirmed_references"] = confirmed_refs
        if not bridge.get("last_card"):
            bridge["last_card"] = rel
        current["knowledge_bridge"] = bridge
        save_state(ctx.project_root, current)
        refresh_status_card(ctx.project_root)
        return added

    added = _locked_mutation(
        ctx, node, stage, ["reference_memory", "references", "knowledge_bridge"], adopt
    )
    if not added:
        return NodeResult(
            outputs=[f"知识卡 {rel} 无新的可采纳证据（去重后 0 条）"],
            logs=["参考记忆未变化"],
        )
    ids = "、".join(str(entry["id"]) for entry in added)
    return NodeResult(
        outputs=[f"已采纳 {len(added)} 条参考方法：{ids}（{rel}）"],
        logs=[f"参考记忆条目 +{len(added)}；知识桥状态 → on"],
    )


def _exec_style_bind(node: Node, ctx: NodeContext) -> NodeResult:
    """把项目已应用的风格卡写入参考记忆（style_reference），绑定 06/08 使用范围。"""
    from contracts import validate as validate_contract
    from core_router.memory import load_memory, memory_path
    from core_router.project import now as project_now

    params = node.params
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将写入风格参考（{params.get('style') or '项目当前风格'}）"],
            logs=["dry-run 不写参考记忆"],
        )

    state = load_state(ctx.project_root)
    style_state = dict(state.get("style") or {})
    applied = style_state.get("status") == "on" and bool(style_state.get("profile_path"))
    if not applied:
        style = str(params.get("style") or "")
        if not style:
            raise NodeError("项目尚未应用风格卡：请先运行风格应用节点，或在此节点给出 style 参数")
        from style_service import StyleService, StyleServiceError

        try:
            _locked_mutation(
                ctx,
                node,
                "",
                ["style_profile"],
                lambda: StyleService().apply(
                    ctx.project_root, style, params.get("tool") or None
                ),
            )
        except StyleServiceError as exc:
            raise NodeError(f"风格应用失败: {exc}") from exc
        state = load_state(ctx.project_root)
        style_state = dict(state.get("style") or {})

    profile_rel = str(style_state.get("profile_path") or "")
    if not profile_rel:
        raise NodeError("风格卡已应用但 state.style.profile_path 为空")
    scopes = [str(item) for item in (params.get("scope") or ["image_06", "camera_08"])]
    stage = str(state.get("stage") or "01")
    if stage not in STAGE_ORDER:
        stage = "08"

    def bind() -> dict[str, Any] | None:
        memory = load_memory(ctx.project_root)
        entries = list(memory.get("entries") or [])
        if any(str(entry.get("local_path")) == profile_rel for entry in entries):
            return None
        profile_path = Path(ctx.project_root) / profile_rel
        style_name = str(params.get("style") or "") or Path(profile_rel).stem
        method = f"风格卡 {profile_rel}"
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            style_name = str(profile.get("name") or style_name)
            palette = [item for item in (profile.get("palette") or []) if isinstance(item, dict)]
            colors = "、".join(
                f"{item.get('name')} {item.get('ratio')}%" for item in palette[:6]
            )
            method = (
                f"风格 {style_name}：{str(profile.get('lighting') or '')[:80]}；"
                f"{str(profile.get('lens') or '')[:80]}；色彩比例 {colors}"
            )
        except (OSError, ValueError):
            method = f"风格卡 {profile_rel}"
        stamp = project_now()
        entry = {
            "id": f"参考方法{_next_reference_id(entries):03d}",
            "status": "enabled",
            "source": f"风格卡 {style_name}",
            "type": "style_reference",
            "local_path": profile_rel,
            "page_hits": "色卡/风格画像",
            "method": method[:500],
            "scope": scopes,
            "stage": stage,
            "binding_facts": [f"项目：{state.get('project')}", f"风格卡：{profile_rel}"],
            "forbidden": ["把风格卡当作剧情参考", "同片混用多套色卡"],
            "confirmed": {"by": "用户", "at": stamp},
            "change_log": [
                {
                    "at": stamp,
                    "action": "created",
                    "note": "复合节点 style_bind 写入风格参考",
                }
            ],
        }
        entries.append(entry)
        memory["entries"] = entries
        problems = validate_contract(memory, schema_name="reference-memory.schema.json")
        if problems:
            raise NodeError("参考记忆校验失败：" + "；".join(problems))
        memory_path(ctx.project_root).write_text(
            json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        current = load_state(ctx.project_root)
        refs = list(current.get("references") or [])
        if entry["id"] not in refs:
            refs.append(entry["id"])
        current["references"] = refs
        save_state(ctx.project_root, current)
        refresh_status_card(ctx.project_root)
        return entry

    entry = _locked_mutation(
        ctx, node, stage, ["reference_memory", "references"], bind
    )
    if entry is None:
        return NodeResult(
            outputs=[f"风格参考已存在：{profile_rel}（跳过）"],
            logs=["参考记忆未变化"],
        )
    return NodeResult(
        outputs=[f"已写入风格参考 {entry['id']}：{entry['source']}"],
        logs=[f"范围 {', '.join(scopes)} · profile {profile_rel}"],
    )


def _exec_generate(node: Node, ctx: NodeContext) -> NodeResult:
    """通过生成平台适配层提交（默认 dry-run，live 需显式参数与环境 key）。"""
    params = node.params
    provider_id = str(params.get("provider") or "mock")
    prompt_path = str(params.get("prompt_path") or "")
    if ctx.dry_run:
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将提交生成任务（provider {provider_id}）"],
            logs=["dry-run 不写生成任务"],
        )
    if not prompt_path:
        raise NodeError("生成节点缺少 prompt_path 参数")
    from generate import GenerateError, get_provider, load_providers, submit as submit_job

    try:
        provider = get_provider(provider_id, load_providers())
        job = submit_job(
            ctx.project_root,
            provider,
            prompt_path=prompt_path,
            model=params.get("model") or None,
            shot=str(params.get("shot") or ""),
            live=bool(params.get("live", False)),
        )
    except GenerateError as exc:
        raise NodeError(f"生成提交失败：{exc}") from exc
    return NodeResult(
        outputs=[
            f"生成任务 {job.get('job_id')}（{job.get('provider')}/{job.get('model')}）状态 {job.get('status')}"
        ],
        logs=[f"dry_run={job.get('dry_run')} · shot={job.get('shot') or '-'}"],
    )


def _exec_generate_refresh(node: Node, ctx: NodeContext) -> NodeResult:
    """查询生成任务平台状态（可选单个任务或批量刷新 submitted）。"""
    params = node.params
    job_id = str(params.get("job_id") or "").strip()
    refresh_all_jobs = bool(params.get("all", not job_id))
    if ctx.dry_run:
        target = f"任务 {job_id}" if job_id else "全部 submitted 任务"
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将刷新生成平台状态：{target}"],
            logs=["dry-run 不访问平台"],
        )
    from generate import GenerateError, refresh as refresh_job, refresh_all

    try:
        if job_id:
            updated = refresh_job(ctx.project_root, job_id)
            return NodeResult(
                outputs=[f"任务 {updated['job_id']} → {updated['status']}"],
                logs=[f"provider {updated.get('provider')}/{updated.get('model')}"],
            )
        if not refresh_all_jobs:
            raise NodeError("刷新节点需要 job_id 或 all=true")
        result = refresh_all(
            ctx.project_root, limit=int(params.get("limit") or 20)
        )
        items = result.get("refreshed") or []
        failed = [item for item in items if not item.get("ok")]
        return NodeResult(
            outputs=[f"已刷新 {len(items)} 个任务（失败 {len(failed)}）"],
            logs=[f"失败：{item['job_id']} {item.get('error')}" for item in failed],
        )
    except GenerateError as exc:
        raise NodeError(f"刷新生成任务失败：{exc}") from exc


def _exec_generate_adopt(node: Node, ctx: NodeContext) -> NodeResult:
    """把 succeeded 任务结果回填为项目产物（可选单个任务或批量）。"""
    params = node.params
    job_id = str(params.get("job_id") or "").strip()
    stage = str(params.get("stage") or "05")
    kind = str(params.get("kind") or "generation")
    note = str(params.get("note") or "")
    if ctx.dry_run:
        target = f"任务 {job_id}" if job_id else "全部 succeeded 任务"
        return NodeResult(
            status="planned",
            outputs=[f"[dry-run] 将回填{target}到阶段 {stage}"],
            logs=["dry-run 不写产物"],
        )
    from generate import GenerateError, adopt as adopt_job, adopt_all

    try:
        if job_id:
            record = adopt_job(
                ctx.project_root, job_id, stage=stage, kind=kind, note=note
            )
            return NodeResult(
                outputs=[f"已回填 {job_id} → {record['artifact']}"],
                logs=[f"结果 URL：{record['result_url']}"],
            )
        if not bool(params.get("all", False)):
            raise NodeError("回填节点需要 job_id 或 all=true")
        result = adopt_all(
            ctx.project_root,
            stage=stage,
            kind=kind,
            note=note,
            limit=int(params.get("limit") or 20),
        )
        items = result.get("jobs") or []
        failed = [item for item in items if not item.get("ok")]
        return NodeResult(
            outputs=[f"已批量回填 {result.get('adopted_count', 0)} 个任务到阶段 {stage}"],
            logs=[f"失败：{item['job_id']} {item.get('error')}" for item in failed],
        )
    except GenerateError as exc:
        raise NodeError(f"回填生成结果失败：{exc}") from exc


EXECUTORS: dict[str, Executor] = {
    "start": _exec_start,
    "stage": _exec_stage,
    "knowledge_search": _exec_knowledge_search,
    "style_apply": _exec_style_apply,
    "style_inject": _exec_style_inject,
    "artifact_register": _exec_artifact_register,
    "check_content": _exec_check_content,
    "condition": _exec_condition,
    "loop": _exec_loop,
    "confirm": _exec_confirm,
    "knowledge_adopt": _exec_knowledge_adopt,
    "style_bind": _exec_style_bind,
    "generate": _exec_generate,
    "generate_refresh": _exec_generate_refresh,
    "generate_adopt": _exec_generate_adopt,
    "export": _exec_export,
    "end": _exec_end,
}


def get_executor(node_type: str) -> Executor:
    executor = EXECUTORS.get(node_type)
    if executor is None:
        raise NodeError(f"节点类型 {node_type} 的执行器未实现")
    return executor
