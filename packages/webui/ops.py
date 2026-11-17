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
from contextlib import redirect_stdout
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
        raise FlowError(f"未知操作: {op_id}")
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
    result = op["handler"](normalized)
    result["op_id"] = op_id
    result["label"] = op["label"]
    return result
