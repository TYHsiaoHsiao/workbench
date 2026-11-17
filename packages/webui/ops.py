"""Web 操作台（M40）：把 CLI 的常用操作以白名单方式暴露给本地 Web UI。

设计原则：
- 只暴露**白名单**操作（op 注册表），不接受任意 shell 命令；
- 每个操作声明参数 schema，前端据此渲染表单；
- 执行时复用 CLI 的 ``cmd_*`` 处理函数（进程内调用，捕获 stdout），返回结构化结果；
- 危险操作（真实提交/回滚）在元数据中标记 ``danger``，前端需二次确认。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from flow import FlowError

_MAX_OUTPUT = 12000


def _p(
    name: str,
    label: str,
    kind: str,
    *,
    required: bool = False,
    default: Any = None,
    choices: list[str] | None = None,
    help: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": kind,
        "required": required,
        "default": default,
        "choices": choices or [],
        "help": help,
    }


def _exit_code(code: Any) -> int:
    if code is None:
        return 0
    try:
        return int(code)
    except (TypeError, ValueError):
        return 1


def _invoke(handler: Callable[[argparse.Namespace], int], **kwargs: Any) -> dict[str, Any]:
    """进程内执行 CLI 处理函数，捕获 stdout 为输出文本。"""
    buffer = io.StringIO()
    code = 1
    try:
        with redirect_stdout(buffer):
            code = _exit_code(handler(argparse.Namespace(**kwargs)))
    except SystemExit as exc:  # argparse 类错误
        code = _exit_code(getattr(exc, "code", 1))
        buffer.write(f"\n[SystemExit] {exc}\n")
    except Exception as exc:  # noqa: BLE001 - 操作台需要返回错误而不是 500
        buffer.write(f"\n[错误] {type(exc).__name__}: {exc}\n")
    output = buffer.getvalue()
    parsed: Any = None
    stripped = output.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
    return {
        "ok": code == 0,
        "exit_code": code,
        "output": output[-_MAX_OUTPUT:],
        "data": parsed,
    }


# ---- 操作历史（M41） ----

_HISTORY_MAX = 50
_HISTORY: list[dict[str, Any]] = []
_HISTORY_ENV = "WORKBENCH_OPS_HISTORY"


def history_path() -> Path:
    override = os.environ.get(_HISTORY_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".workbench" / "ops-history.jsonl"


def _persist_history(entry: dict[str, Any]) -> None:
    try:
        path = history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _load_history() -> None:
    path = history_path()
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return
    for line in lines[-_HISTORY_MAX:]:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("op_id"):
            _HISTORY.append(entry)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _record_history(
    op_id: str,
    label: str,
    *,
    started_at: str,
    duration_ms: int,
    ok: bool,
    exit_code: int = 0,
    error: str = "",
) -> dict[str, Any]:
    entry = {
        "op_id": op_id,
        "label": label,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "ok": ok,
        "exit_code": exit_code,
    }
    if error:
        entry["error"] = error
    _HISTORY.append(entry)
    del _HISTORY[: max(0, len(_HISTORY) - _HISTORY_MAX)]
    _persist_history(entry)
    return entry


def list_history(limit: int = 20) -> list[dict[str, Any]]:
    """返回最近的操作历史（新→旧，最多 50 条）。"""
    try:
        raw = int(limit)
    except (TypeError, ValueError):
        raw = 20
    limit = max(1, min(raw, _HISTORY_MAX))
    return list(reversed(_HISTORY))[:limit]


# ---- 处理器（延迟导入 CLI，避免 server 启动即加载全部命令） ----


def _cli():
    # 注意：``from cli import main`` 会拿到包内导出的 main 函数；这里需要模块本身。
    from importlib import import_module

    return import_module("cli.main")


def run_quickstart(params: dict[str, Any]) -> dict[str, Any]:
    cli = _cli()
    return _invoke(
        cli.cmd_quickstart,
        name=params["name"],
        project_root=params.get("project_root") or None,
        entry=params.get("entry") or "A",
        mode=params.get("mode") or "full",
        template=params.get("template") or "tpl-full-flow",
        skip_graph=False,
        force=False,
        demo=bool(params.get("demo", True)),
        json=True,
    )


def run_practical_check(params: dict[str, Any]) -> dict[str, Any]:
    cli = _cli()
    return _invoke(
        cli.cmd_practical_check,
        project=params["project"],
        fix=bool(params.get("fix", True)),
        source=params.get("source") or None,
        json=True,
    )


def run_index_build(params: dict[str, Any]) -> dict[str, Any]:
    cli = _cli()
    return _invoke(
        cli.cmd_index_build,
        source=params["source"],
        out=params.get("out") or None,
        incremental=bool(params.get("incremental", False)),
        index_id=params.get("index_id") or None,
        json=True,
    )


def run_index_info(params: dict[str, Any]) -> dict[str, Any]:
    cli = _cli()
    return _invoke(cli.cmd_index_info, out=params.get("out") or None, json=True)


def run_index_verify(params: dict[str, Any]) -> dict[str, Any]:
    cli = _cli()
    return _invoke(cli.cmd_index_verify, out=params.get("out") or None, json=True)


def run_index_search(params: dict[str, Any]) -> dict[str, Any]:
    cli = _cli()
    return _invoke(
        cli.cmd_index_search,
        query=params["query"],
        limit=int(params.get("limit") or 8),
        out=params.get("out") or None,
        min_score=params.get("min_score"),
        max_per_file=params.get("max_per_file"),
        json=True,
    )


def run_generate_providers(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_generate_providers, json=True)


def run_generate_plan(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_generate_plan,
        provider=params["provider"],
        project=params["project"],
        prompt=params.get("prompt") or None,
        prompt_file=params.get("prompt_file") or "05_shots/shot-01-prompt.md",
        model=params.get("model") or None,
        shot=params.get("shot") or None,
        json=True,
    )


def run_generate_submit(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_generate_submit,
        provider=params["provider"],
        project=params["project"],
        prompt=params.get("prompt") or None,
        prompt_file=params.get("prompt_file") or "05_shots/shot-01-prompt.md",
        model=params.get("model") or None,
        shot=params.get("shot") or None,
        live=bool(params.get("live", False)),
        json=True,
    )


def run_batch(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_batch,
        project=params["project"],
        graphs=params.get("graphs") or None,
        all=bool(params.get("all", True)),
        dry_run=True,
        yes=True,
        auto_retry=int(params.get("auto_retry") or 0),
        fail_fast=False,
        parallel=False,
        workers=2,
        limit=int(params.get("limit") or 20),
        json=True,
    )


def run_queue_add(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_queue_add,
        project=params["project"],
        graphs=params.get("graphs") or None,
        all=bool(params.get("all", True)),
        dry_run=True,
        auto_retry=int(params.get("auto_retry") or 0),
        fail_fast=False,
        parallel=False,
        workers=2,
        json=True,
    )


def run_queue_run(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_queue_run,
        project=params["project"],
        all_projects=False,
        limit=int(params.get("limit") or 5),
        notify_cmd=None,
        json=True,
    )


def run_batch_report(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_batch_report,
        project=params["project"],
        format=params.get("format") or "md",
        limit=int(params.get("limit") or 20),
        json=True,
    )


def run_snapshot_create(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_rollback_create,
        project=params["project"],
        label=params.get("label") or "",
        json=True,
    )


def run_snapshot_list(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_rollback_list, project=params["project"], json=True)


def run_rollback_apply(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_rollback_apply,
        project=params["project"],
        snapshot=params["snapshot"],
        dry_run=bool(params.get("dry_run", True)),
        json=True,
    )


def run_project_list(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_project_list, root=params.get("root") or None, json=True)


def run_project_summary(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_project_summary, project=params["project"], json=True)


def run_generate_refresh(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_generate_refresh,
        project=params["project"],
        job_id=params.get("job_id") or None,
        all=bool(params.get("all", True)),
        limit=int(params.get("limit") or 20),
        json=True,
    )


def run_batch_report_push(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_batch_report,
        project=params["project"],
        format=params.get("format") or "md",
        limit=int(params.get("limit") or 20),
        push=True,
        webhook_url=params["webhook_url"],
        webhook_format=params.get("webhook_format") or "generic",
        webhook_retries=int(params.get("webhook_retries") or 0),
        json=True,
    )


def run_queue_alerts(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_queue_alerts,
        project=params["project"],
        limit=int(params.get("limit") or 50),
        webhook_url=None,
        fail_if_failures=False,
        webhook_format="generic",
        webhook_retries=0,
        dedupe_minutes=30,
        json=True,
    )


def run_queue_alerts_push(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_queue_alerts,
        project=params["project"],
        limit=int(params.get("limit") or 50),
        webhook_url=params["webhook_url"],
        fail_if_failures=False,
        webhook_format=params.get("format") or "generic",
        webhook_retries=int(params.get("webhook_retries") or 0),
        dedupe_minutes=int(params.get("dedupe_minutes") if params.get("dedupe_minutes") is not None else 30),
        json=True,
    )


def run_flow_batches(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_flow_batches, project=params["project"], limit=int(params.get("limit") or 10), json=True)


def run_doctor(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_doctor, json=True)


# ---- 注册表 ----


def run_init_project(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_init,
        name=params["name"],
        project_root=params.get("project_root") or None,
        entry=params.get("entry") or "A",
        mode=params.get("mode") or "full",
        force=bool(params.get("force")),
        json=True,
    )


def run_quickstart_plain(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_quickstart,
        name=params["name"],
        project_root=params.get("project_root") or None,
        entry=params.get("entry") or "A",
        mode=params.get("mode") or "full",
        template=params.get("template") or "tpl-full-flow",
        skip_graph=bool(params.get("skip_graph")),
        force=bool(params.get("force")),
        demo=False,
        json=True,
    )


def run_route(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_route, text=params["text"], json=True)


def run_gate_list(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_gate,
        project=params["project"],
        action="list",
        gate_id=None,
        note=None,
        json=True,
    )


def run_gate_set(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_gate,
        project=params["project"],
        action=params.get("action") or "pass",
        gate_id=params["gate_id"],
        note=params.get("note") or "",
        json=True,
    )


def run_next_stage(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_next, project=params["project"], json=True)


def run_flow_new(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_new,
        project=params["project"],
        name=params["name"],
        graph=params.get("graph") or None,
        template=params.get("template") or "tpl-full-flow",
        force=False,
        json=True,
    )


def run_flow_list(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(_cli().cmd_flow_list, project=params["project"], json=True)


def run_style_list_op(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_style_list,
        category=params.get("category") or None,
        quality=params.get("quality") or None,
        json=True,
    )


def run_style_show(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_style_show,
        ref=params["ref"],
        tool=params.get("tool") or None,
        json=True,
    )


def run_style_apply(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_style_apply,
        project=params["project"],
        ref=params["ref"],
        tool=params.get("tool") or None,
        json=True,
    )


def run_style_inject(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_style_inject,
        project=params["project"],
        ref=params["ref"],
        stage=params.get("stage") or "06",
        tool=params.get("tool") or None,
        prompt_file=params["prompt_file"],
        json=True,
    )


def run_flow_run(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_run,
        project=params["project"],
        graph=params["graph"],
        dry_run=bool(params.get("dry_run", True)),
        yes=bool(params.get("yes", True)),
        mode=params.get("mode") or "full",
        node=params.get("node") or None,
        retries=int(params.get("retries") or 0),
        json=True,
    )


def run_flow_runs(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_flow_runs,
        project=params["project"],
        limit=int(params.get("limit") or 20),
        json=True,
    )


def run_artifact_register(params: dict[str, Any]) -> dict[str, Any]:
    raw = str(params.get("paths") or "").replace("，", ",")
    paths = [item.strip() for item in raw.split(",") if item.strip()]
    return _invoke(
        _cli().cmd_artifact_register,
        project=params["project"],
        stage=params["stage"],
        kind=params.get("kind") or "generation",
        path=paths,
        note=params.get("note") or "",
        next_action=params.get("next_action") or None,
        json=True,
    )


def run_generate_jobs(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_generate_jobs,
        project=params["project"],
        limit=int(params.get("limit") or 20),
        json=True,
    )


def run_generate_retry_op(params: dict[str, Any]) -> dict[str, Any]:
    live = bool(params.get("live"))
    return _invoke(
        _cli().cmd_generate_retry,
        project=params["project"],
        job_id=params["job_id"],
        live=live,
        dry_run=bool(params.get("dry_run", True)),
        json=True,
    )


def run_generate_adopt_op(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_generate_adopt,
        project=params["project"],
        job_id=params.get("job_id") or None,
        all=bool(params.get("all", True)),
        stage=params.get("stage") or "05",
        kind=params.get("kind") or "generation",
        note=params.get("note") or "",
        limit=int(params.get("limit") or 20),
        json=True,
    )


def run_reference_list_op(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_reference_list,
        project=params["project"],
        stage=params.get("stage") or None,
        json=True,
    )


def run_project_export(params: dict[str, Any]) -> dict[str, Any]:
    return _invoke(
        _cli().cmd_export,
        project=params["project"],
        out=params.get("out") or None,
        force=bool(params.get("force")),
        json=True,
    )


OPS: list[dict[str, Any]] = [
    {
        "id": "quickstart_demo",
        "label": "一键开工（含演示素材）",
        "category": "开工",
        "description": "创建项目 + 默认流程图 + 演示剧本与首条提示词（M38/M39）。",
        "params": [
            _p("name", "项目名称", "text", required=True, help="例如：我的短片"),
            _p("project_root", "项目根目录（可选）", "text", help="默认文档目录下的工作台 projects/"),
        ],
        "handler": run_quickstart,
    },
    {
        "id": "practical_check",
        "label": "实操自检 + 自动修复",
        "category": "开工",
        "description": "八项实操检查；缺流程图时自动补建默认模板。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("fix", "自动修复", "bool", default=True),
            _p("source", "知识库目录（可选，用于建索引）", "text"),
        ],
        "handler": run_practical_check,
    },
    {
        "id": "project_list",
        "label": "项目总览",
        "category": "项目",
        "description": "列出项目根目录下所有项目与阶段。",
        "params": [_p("root", "项目根目录（可选）", "text")],
        "handler": run_project_list,
    },
    {
        "id": "index_build",
        "label": "构建本地索引",
        "category": "知识库",
        "description": "按契约从知识库子目录构建 FTS5 索引（较耗时，建议选子目录）。",
        "params": [
            _p("source", "知识库目录", "text", required=True),
            _p("out", "索引输出目录（可选）", "text"),
            _p("incremental", "增量构建", "bool", default=False),
        ],
        "handler": run_index_build,
    },
    {
        "id": "index_info",
        "label": "索引信息",
        "category": "知识库",
        "description": "查看本地索引元数据与规模。",
        "params": [_p("out", "索引目录（可选）", "text")],
        "handler": run_index_info,
    },
    {
        "id": "index_verify",
        "label": "索引校验",
        "category": "知识库",
        "description": "校验索引结构、FTS 一致性与元数据契约。",
        "params": [_p("out", "索引目录（可选）", "text")],
        "handler": run_index_verify,
    },
    {
        "id": "index_search",
        "label": "索引检索",
        "category": "知识库",
        "description": "用混合检索在本地索引中查证据片段（M24/M27/M30）。",
        "params": [
            _p("query", "查询词", "text", required=True),
            _p("limit", "返回条数", "int", default=8),
            _p("out", "索引目录（可选）", "text"),
        ],
        "handler": run_index_search,
    },
    {
        "id": "generate_providers",
        "label": "生成平台列表",
        "category": "生成",
        "description": "列出可用 provider 与 key 配置状态。",
        "params": [],
        "handler": run_generate_providers,
    },
    {
        "id": "generate_plan",
        "label": "生成预检（plan）",
        "category": "生成",
        "description": "校验提示词并输出 dry-run 计划（不提交）。",
        "params": [
            _p("provider", "平台", "enum", required=True, default="mock",
               choices=["mock", "seedance_2_0", "seedance_2_5", "minimax_h3"]),
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("prompt_file", "提示词文件（项目内相对路径）", "text", default="05_shots/shot-01-prompt.md"),
            _p("model", "模型（可选）", "text"),
            _p("shot", "镜头号（可选）", "text"),
            _p("prompt", "提示词正文（可选，覆盖文件）", "text"),
        ],
        "handler": run_generate_plan,
    },
    {
        "id": "generate_submit",
        "label": "生成提交",
        "category": "生成",
        "description": "提交生成任务；live=false 时仅 dry-run 记录。",
        "params": [
            _p("provider", "平台", "enum", required=True, default="mock",
               choices=["mock", "seedance_2_0", "seedance_2_5", "minimax_h3"]),
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("prompt_file", "提示词文件（项目内相对路径）", "text", default="05_shots/shot-01-prompt.md"),
            _p("model", "模型（可选）", "text"),
            _p("shot", "镜头号（可选）", "text"),
            _p("live", "真实提交（需 key）", "bool", default=False),
        ],
        "handler": run_generate_submit,
    },
    {
        "id": "batch_run",
        "label": "批量预演",
        "category": "流程",
        "description": "对项目全部流程图执行 dry-run 批次。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("all", "全部流程图", "bool", default=True),
            _p("graphs", "指定图（逗号分隔，可选）", "text"),
            _p("auto_retry", "失败重试次数", "int", default=0),
        ],
        "handler": run_batch,
    },
    {
        "id": "queue_add",
        "label": "加入队列",
        "category": "队列",
        "description": "把流程图加入队列（dry-run）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("all", "全部流程图", "bool", default=True),
            _p("graphs", "指定图（逗号分隔，可选）", "text"),
            _p("auto_retry", "失败重试次数", "int", default=0),
        ],
        "handler": run_queue_add,
    },
    {
        "id": "queue_run",
        "label": "运行队列",
        "category": "队列",
        "description": "顺序执行队列中的待运行条目。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("limit", "本轮最多执行条数", "int", default=5),
        ],
        "handler": run_queue_run,
    },
    {
        "id": "batch_report",
        "label": "批次报表",
        "category": "流程",
        "description": "导出最近批次趋势报表（md/csv/html）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("format", "格式", "enum", default="md", choices=["md", "csv", "html"]),
            _p("limit", "批次数", "int", default=20),
        ],
        "handler": run_batch_report,
    },
    {
        "id": "snapshot_create",
        "label": "创建快照",
        "category": "快照",
        "description": "保存项目状态快照（可用于回滚）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("label", "说明（可选）", "text"),
        ],
        "handler": run_snapshot_create,
    },
    {
        "id": "snapshot_list",
        "label": "快照列表",
        "category": "快照",
        "description": "列出项目快照。",
        "params": [_p("project", "项目（路径或名称）", "text", required=True)],
        "handler": run_snapshot_list,
    },
    {
        "id": "rollback_apply",
        "label": "回滚到快照",
        "category": "快照",
        "description": "把项目恢复为指定快照（默认 dry-run，关闭后真实覆盖）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("snapshot", "快照 ID", "text", required=True),
            _p("dry_run", "仅预演", "bool", default=True),
        ],
        "danger": True,
        "confirm": "回滚会覆盖项目当前文件（dry_run=false 时）。确认执行？",
        "handler": run_rollback_apply,
    },
    {
        "id": "project_summary",
        "label": "项目摘要",
        "category": "项目",
        "description": "查看项目阶段、产物登记与流程图概览（M41）。",
        "params": [_p("project", "项目（路径或名称）", "text", required=True)],
        "handler": run_project_summary,
    },
    {
        "id": "generate_refresh",
        "label": "刷新生成任务",
        "category": "生成",
        "description": "查询平台任务状态并回填（M41；默认刷新全部 submitted 任务）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("job_id", "任务 ID（可选，留空配合“全部”）", "text"),
            _p("all", "刷新全部 submitted 任务", "bool", default=True),
            _p("limit", "最多刷新数", "int", default=20),
        ],
        "handler": run_generate_refresh,
    },
    {
        "id": "batch_report_push",
        "label": "推送批次报表",
        "category": "流程",
        "description": "生成批次趋势报表并外送到 webhook（M41；支持飞书格式）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("webhook_url", "Webhook 地址", "text", required=True),
            _p("format", "报表格式", "enum", default="md", choices=["md", "csv", "html"]),
            _p("webhook_format", "推送格式", "enum", default="generic", choices=["generic", "feishu", "feishu_card"]),
            _p("webhook_retries", "重试次数", "int", default=0),
            _p("limit", "批次数", "int", default=20),
        ],
        "handler": run_batch_report_push,
    },
    {
        "id": "queue_alerts",
        "label": "队列失败告警",
        "category": "队列",
        "description": "聚合最近队列失败通知，并展示静默窗口状态（M41）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("limit", "通知条数", "int", default=50),
        ],
        "handler": run_queue_alerts,
    },
    {
        "id": "queue_alerts_push",
        "label": "推送队列告警摘要",
        "category": "队列",
        "description": "把队列失败告警摘要外送到 webhook（支持静默窗口，M41）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("webhook_url", "Webhook 地址", "text", required=True),
            _p("format", "推送格式", "enum", default="generic", choices=["generic", "feishu", "feishu_card"]),
            _p("webhook_retries", "重试次数", "int", default=0),
            _p("dedupe_minutes", "静默窗口（分钟，0=关闭）", "int", default=30),
            _p("limit", "通知条数", "int", default=50),
        ],
        "handler": run_queue_alerts_push,
    },
    {
        "id": "flow_batches",
        "label": "批次历史",
        "category": "流程",
        "description": "列出最近的批次运行记录（M41）。",
        "params": [
            _p("project", "项目（路径或名称）", "text", required=True),
            _p("limit", "条数", "int", default=10),
        ],
        "handler": run_flow_batches,
    },
    {
        "id": "doctor",
        "label": "环境自检（doctor）",
        "category": "运维",
        "description": "十项自检：Python/布局/契约/注册表/风格库/流程/生成/索引/品牌词表（M41）。",
        "params": [],
        "handler": run_doctor,
    },    {"id": "init_project", "label": "创建项目（init）", "category": "开工",
     "description": "按入口/模式创建项目骨架（state v2），可指定项目根目录。",
     "params": [
         _p("name", "项目名称", "text", required=True),
         _p("project_root", "项目根目录（可选）", "text"),
         _p("entry", "项目入口", "enum", default="A", choices=["A", "B", "C", "D"]),
         _p("mode", "启动模式", "enum", default="full", choices=["full", "stage", "relay", "revise"]),
     ],
     "handler": run_init_project},
    {"id": "quickstart", "label": "一键开工（不写演示素材）", "category": "开工",
     "description": "创建项目 + 默认流程图，不写入演示剧本与示例提示词。",
     "params": [
         _p("name", "项目名称", "text", required=True),
         _p("project_root", "项目根目录（可选）", "text"),
         _p("entry", "项目入口", "enum", default="A", choices=["A", "B", "C", "D"]),
         _p("mode", "启动模式", "enum", default="full", choices=["full", "stage", "relay", "revise"]),
         _p("skip_graph", "不创建默认流程图", "bool", default=False),
     ],
     "handler": run_quickstart_plain},
    {"id": "route", "label": "意图路由（route）", "category": "阶段",
     "description": "把一句话需求路由到对应 Skill/阶段命令建议。",
     "params": [_p("text", "需求描述", "text", required=True)],
     "handler": run_route},
    {"id": "gate_list", "label": "查看阶段门禁", "category": "阶段",
     "description": "列出当前阶段门禁及通过状态。",
     "params": [_p("project", "项目路径或名称", "text", required=True)],
     "handler": run_gate_list},
    {"id": "gate_set", "label": "通过/失败/豁免门禁", "category": "阶段",
     "description": "写入一个门禁结果（会修改项目状态）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("gate_id", "门禁 ID", "text", required=True),
         _p("action", "动作", "enum", default="pass", choices=["pass", "fail", "waive"]),
         _p("note", "备注", "text"),
     ],
     "confirm": "会写入门禁状态（state.json），确定继续？",
     "handler": run_gate_set},
    {"id": "next_stage", "label": "推进到下一阶段", "category": "阶段",
     "description": "推进项目阶段并写状态文件。",
     "params": [_p("project", "项目路径或名称", "text", required=True)],
     "confirm": "会推进阶段并写 state.json，确定继续？",
     "handler": run_next_stage},
    {"id": "flow_new", "label": "新建流程图", "category": "流程",
     "description": "按模板创建一张流程图。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("name", "流程图名称", "text", required=True),
         _p("graph", "图 ID（可选）", "text"),
         _p("template", "模板", "text", default="tpl-full-flow"),
     ],
     "handler": run_flow_new},
    {"id": "flow_list", "label": "流程图列表", "category": "流程",
     "description": "列出项目内的流程图。",
     "params": [_p("project", "项目路径或名称", "text", required=True)],
     "handler": run_flow_list},
    {"id": "flow_run", "label": "运行流程图", "category": "流程",
     "description": "运行流程图（默认 dry-run 预演）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("graph", "图 ID", "text", required=True),
         _p("dry_run", "预演（不写盘）", "bool", default=True),
         _p("mode", "运行模式", "enum", default="full", choices=["full", "stage", "single"]),
         _p("node", "目标节点（可空）", "text"),
         _p("retries", "节点重试次数", "int", default=0),
     ],
     "handler": run_flow_run},
    {"id": "flow_runs", "label": "运行记录", "category": "流程",
     "description": "列出最近的流程图运行记录。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("limit", "条数", "int", default=20),
     ],
     "handler": run_flow_runs},
    {"id": "style_list", "label": "风格库列表", "category": "风格",
     "description": "列出导演风格卡（可按类别/质量过滤）。",
     "params": [_p("category", "类别（可空）", "text"), _p("quality", "质量等级 A/B/C（可空）", "text")],
     "handler": run_style_list_op},
    {"id": "style_show", "label": "查看风格卡", "category": "风格",
     "description": "查看某导演风格卡与工具适配提示词。",
     "params": [
         _p("ref", "风格编号/名称", "text", required=True),
         _p("tool", "目标工具（可空）", "text"),
     ],
     "handler": run_style_show},
    {"id": "style_apply", "label": "应用风格卡到项目", "category": "风格",
     "description": "把风格卡应用到项目，生成风格画像。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("ref", "风格编号/名称", "text", required=True),
         _p("tool", "目标工具（可空）", "text"),
     ],
     "handler": run_style_apply},
    {"id": "style_inject", "label": "风格注入提示词", "category": "风格",
     "description": "把风格卡注入一条提示词文件。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("ref", "风格编号/名称", "text", required=True),
         _p("prompt_file", "提示词文件（项目内）", "text", required=True),
         _p("stage", "阶段", "enum", default="06", choices=["06", "08"]),
         _p("tool", "目标工具（可空）", "text"),
     ],
     "handler": run_style_inject},
    {"id": "artifact_register", "label": "登记产物", "category": "项目",
     "description": "把文件登记为阶段产物（写入 state.stage_artifacts）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("stage", "阶段", "text", required=True),
         _p("kind", "产物类型", "text", default="generation"),
         _p("paths", "文件路径（逗号分隔，项目内）", "text", required=True),
         _p("note", "备注", "text"),
         _p("next_action", "下一步提示", "text"),
     ],
     "handler": run_artifact_register},
    {"id": "reference_list", "label": "参考记忆列表", "category": "项目",
     "description": "查看项目参考记忆（可按阶段过滤）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("stage", "阶段（可空）", "text"),
     ],
     "handler": run_reference_list_op},
    {"id": "project_export", "label": "导出项目", "category": "项目",
     "description": "把项目导出为 zip 归档。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("out", "输出 zip 路径（可空）", "text"),
         _p("force", "覆盖已存在文件", "bool", default=False),
     ],
     "handler": run_project_export},
    {"id": "generate_jobs", "label": "生成任务列表", "category": "生成",
     "description": "列出项目生成任务（dry-run/live 记录）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("limit", "条数", "int", default=20),
     ],
     "handler": run_generate_jobs},
    {"id": "generate_retry", "label": "重试生成任务", "category": "生成",
     "description": "重试失败/取消的生成任务（默认 dry-run）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("job_id", "任务 ID", "text", required=True),
         _p("live", "真实提交", "bool", default=False),
     ],
     "handler": run_generate_retry_op},
    {"id": "generate_adopt", "label": "回填生成结果", "category": "生成",
     "description": "把成功的生成结果回填为项目产物（默认全部）。",
     "params": [
         _p("project", "项目路径或名称", "text", required=True),
         _p("job_id", "任务 ID（all=false 时必填）", "text"),
         _p("all", "回填全部已成功任务", "bool", default=True),
         _p("stage", "回填阶段", "enum", default="05", choices=["01", "02", "03", "04", "05", "06", "07", "08"]),
         _p("kind", "产物类型", "text", default="generation"),
         _p("note", "备注", "text"),
         _p("limit", "条数", "int", default=20),
     ],
     "handler": run_generate_adopt_op},

]

OPS_BY_ID = {item["id"]: item for item in OPS}


def list_ops() -> list[dict[str, Any]]:
    """返回可安全下发给前端的操作元数据（不含 handler）。"""
    public = []
    for item in OPS:
        entry = {key: value for key, value in item.items() if key != "handler"}
        entry["params"] = [dict(param) for param in item["params"]]
        public.append(entry)
    return public


def run_op(op_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    op = OPS_BY_ID.get(op_id)
    if op is None:
        message = f"未知操作: {op_id}"
        _record_history(
            str(op_id),
            str(op_id),
            started_at=_now(),
            duration_ms=0,
            ok=False,
            exit_code=1,
            error=message,
        )
        raise FlowError(message)
    given = dict(params or {})
    missing = [
        param["name"]
        for param in op["params"]
        if param["required"] and not str(given.get(param["name"]) or "").strip()
    ]
    if missing:
        raise FlowError(f"缺少参数: {', '.join(missing)}")
    normalized: dict[str, Any] = {}
    for param in op["params"]:
        name = param["name"]
        value = given.get(name, param.get("default"))
        if value in (None, ""):
            normalized[name] = param.get("default")
            continue
        if param["type"] == "int":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise FlowError(f"参数 {name} 需要整数: {value}") from exc
        elif param["type"] == "bool":
            value = bool(value) if not isinstance(value, str) else value.strip().lower() not in ("0", "false", "no", "")
        elif param["type"] == "enum":
            if value not in (param.get("choices") or []):
                raise FlowError(f"参数 {name} 取值无效: {value}")
        else:
            value = str(value).strip()
        normalized[name] = value
    started_at = _now()
    started = time.perf_counter()
    try:
        result = op["handler"](normalized)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _record_history(
            op_id,
            op["label"],
            started_at=started_at,
            duration_ms=duration_ms,
            ok=False,
            exit_code=1,
            error=str(exc),
        )
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    result["op_id"] = op_id
    result["label"] = op["label"]
    result["duration_ms"] = duration_ms
    _record_history(
        op_id,
        op["label"],
        started_at=started_at,
        duration_ms=duration_ms,
        ok=bool(result.get("ok")),
        exit_code=int(result.get("exit_code") or 0),
    )
    return result


_BATCH_MAX = 20


def run_ops_batch(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """顺序执行多个操作（M41）；单次最多 20 个，单项失败不中断整体。"""
    if not isinstance(items, list) or not items:
        raise FlowError("批量执行需要非空 items 列表")
    if len(items) > _BATCH_MAX:
        raise FlowError(f"单次批量最多 {_BATCH_MAX} 个操作")
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise FlowError(f"第 {index + 1} 项格式无效（需要对象）")
        op_id = str(item.get("op_id") or "").strip()
        params = item.get("params") or {}
        if not op_id:
            raise FlowError(f"第 {index + 1} 项缺少 op_id")
        try:
            result = run_op(op_id, params)
            results.append(
                {
                    "index": index + 1,
                    "op_id": op_id,
                    "label": result.get("label"),
                    "ok": bool(result.get("ok")),
                    "exit_code": int(result.get("exit_code") or 0),
                    "duration_ms": int(result.get("duration_ms") or 0),
                    "output": str(result.get("output") or "")[-2000:],
                    "data": result.get("data"),
                }
            )
        except FlowError as exc:
            results.append(
                {
                    "index": index + 1,
                    "op_id": op_id,
                    "ok": False,
                    "error": str(exc),
                }
            )
    return {
        "ok": all(item.get("ok") for item in results),
        "count": len(results),
        "results": results,
    }


_load_history()
