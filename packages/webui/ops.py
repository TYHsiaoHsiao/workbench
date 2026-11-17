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
import time
from contextlib import redirect_stdout
from datetime import datetime
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
    },
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
