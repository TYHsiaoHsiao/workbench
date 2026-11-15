"""命令行：version / doctor / check / brand-guard / init / route / gate / next /
validate / install / migrate / upgrade / knowledge。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from brand_guard import BrandGuardError, load_config, load_wordlist
from brand_guard.guard import scan as brand_scan
from contracts import CONTRACT_VERSION, list_schemas, load_schema, validate, validate_file
from core_router import (
    GateError,
    MemoryError,
    MigrationError,
    ProjectError,
    RegistryError,
    advance,
    can_advance,
    classify,
    create_project,
    ensure_stage_gates,
    entries_for_stage,
    export_project,
    fail_gate,
    gate_detail,
    load_memory,
    load_registry,
    load_rules,
    load_state,
    migrate_project,
    pass_gate,
    refresh_status_card,
    register_artifacts,
    restore_project,
    save_state,
    summarize_memory,
    update_knowledge_bridge,
    upgrade_project_rules,
    validate_registry,
    waive_gate,
)
from core_router.check import content_checks
from core_router.project import PROJECT_DIRS, default_projects_root
from core_router.registry import REPO_ROOT as WORKBENCH_ROOT
from core_router.state import validate_state
from installer import InstallerError, install_skills
from knowledge_service import KnowledgeService, KnowledgeServiceError
from flow import (
    FlowError,
    Runner,
    build_replay,
    compare_runs,
    format_compare_text,
    default_graph,
    format_replay_text,
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
from style_service import (
    AdapterError,
    StyleRegistryError,
    StyleService,
    StyleServiceError,
    load_style_registry,
    validate_prompt,
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ENV = 3


def _read_version() -> str:
    version_file = WORKBENCH_ROOT / "VERSION"
    if not version_file.is_file():
        return "0.0.0"
    return version_file.read_text(encoding="utf-8").strip()


def _print(text: str = "") -> None:
    print(text)


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        _print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_version(args: argparse.Namespace) -> int:
    _print(f"workbench {_read_version()} (contracts v{CONTRACT_VERSION})")
    return EXIT_OK


def _check_python() -> tuple[bool, str]:
    good = sys.version_info >= (3, 10)
    return good, f"Python {sys.version_info.major}.{sys.version_info.minor}（要求 >= 3.10）"


def _check_wordlist() -> tuple[bool, str]:
    try:
        config = load_config()
        terms = load_wordlist(WORKBENCH_ROOT / config["wordlist"])
        return True, f"品牌词表可解码（{len(terms)} 项）"
    except BrandGuardError as exc:
        return False, str(exc)


def _check_registry() -> tuple[bool, str]:
    errors = validate_registry()
    if errors:
        return False, "注册表校验失败: " + "; ".join(errors)
    return True, "阶段注册表 01-08 校验通过"


def _check_intent() -> tuple[bool, str]:
    try:
        rules = load_rules()
        stages = len(rules.get("stages", {}))
        maintenance = len(rules.get("maintenance", {}))
        return True, f"意图规则可加载（{stages} 个阶段、{maintenance} 个维护口令）"
    except Exception as exc:  # noqa: BLE001 - 自检需要聚合任意异常
        return False, str(exc)


def _check_schemas() -> tuple[bool, str]:
    names = list_schemas()
    if len(names) < 6:
        return False, f"契约 schema 数量不足: {names}"
    for name in names:
        load_schema(name)
    return True, f"契约 schema 可加载（{len(names)} 个）"


def _check_layout() -> tuple[bool, str]:
    required = [
        "workbench.py",
        "content/stage-registry.json",
        "content/intent-rules.json",
        "content/style-registry.json",
        "content/flow-node-types.json",
        "content/flow-templates.json",
        "config/brand-guard.json",
    ]
    missing = [rel for rel in required if not (WORKBENCH_ROOT / rel).is_file()]
    if missing:
        return False, "缺少文件: " + ", ".join(missing)
    return True, "仓库骨架完整"


def _check_style_registry() -> tuple[bool, str]:
    try:
        registry = load_style_registry()
        summary = registry.summary()
        grades = summary.get("grade_counts") or {}
        return True, (
            f"风格注册表 {summary['directors']} 条 / {summary['categories']} 类"
            f"（A {grades.get('A', 0)}、B {grades.get('B', 0)}、C {grades.get('C', 0)}）"
        )
    except StyleRegistryError as exc:
        return False, str(exc)


def _check_flow() -> tuple[bool, str]:
    try:
        types = load_node_types()
        templates = load_templates()
    except FlowError as exc:
        return False, str(exc)
    except Exception as exc:  # TemplateError
        return False, str(exc)
    required = [
        "flow-graph.schema.json",
        "flow-node-types.schema.json",
        "flow-run.schema.json",
        "flow-templates.schema.json",
    ]
    schemas = set(list_schemas())
    missing = [name for name in required if name not in schemas]
    if missing:
        return False, "缺少流程契约: " + ", ".join(missing)
    return True, f"流程节点类型 {len(types)} 个、模板 {len(templates)} 个、契约 {len(required)} 份"


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = [
        ("python", _check_python()),
        ("layout", _check_layout()),
        ("contracts", _check_schemas()),
        ("registry", _check_registry()),
        ("intent-rules", _check_intent()),
        ("style-registry", _check_style_registry()),
        ("flow", _check_flow()),
        ("brand-wordlist", _check_wordlist()),
    ]
    failures = 0
    for name, (ok, detail) in checks:
        flag = "OK" if ok else "FAIL"
        _print(f"[{flag}] {name}: {detail}")
        if not ok:
            failures += 1
    _emit({"ok": failures == 0, "checks": len(checks), "failures": failures}, args.json)
    return EXIT_OK if failures == 0 else EXIT_ENV


_ARTIFACT_TOKEN = re.compile(r"[0-9A-Za-z_\u4e00-\u9fff./\-]+\.(?:md|json|txt)")
_SCENE_ROW = re.compile(r"^\|\s*(1-0[1-8])\b")
_SCENE_BUDGET = re.compile(r"场次时长预算[：:]\s*(\d+)\s*s")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _scene_seconds(text: str) -> dict[str, int]:
    """从以 `| 1-0X |` 开头的表格行里取第一段「N s / N 秒」。"""
    result: dict[str, int] = {}
    for line in text.splitlines():
        match = _SCENE_ROW.match(line)
        if not match:
            continue
        found = re.findall(r"(\d+)\s*(?:s|秒)(?![A-Za-z0-9])", line)
        if found:
            result[match.group(1)] = int(found[0])
    return result


def _content_checks(project_dir: Path, state: dict[str, Any]) -> tuple[list[str], list[str]]:
    """阶段内容一致性检查（委托 core_router.check，流程节点复用同一实现）。"""
    return content_checks(project_dir, state)


def cmd_check(args: argparse.Namespace) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    registry_path = Path(args.registry) if args.registry else None
    errors.extend(validate_registry(registry_path))
    report: dict[str, Any] = {"registry_errors": list(errors)}
    state: dict[str, Any] | None = None

    if args.project:
        project_dir = Path(args.project)
        state_path = project_dir / "00_project" / "state.json"
        if not state_path.is_file():
            errors.append(f"{state_path}: 缺少项目状态文件")
        else:
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{state_path}: JSON 解析失败: {exc}")
                state = None
            if state is not None:
                state_errors = validate_state(state)
                errors.extend(f"{state_path}{' ' + err}" for err in state_errors)
        memory_path = project_dir / "00_project" / "reference-memory.json"
        if memory_path.is_file():
            errors.extend(validate_file(memory_path, "reference-memory"))
        if args.content and state is not None:
            content_errors, content_warnings = _content_checks(project_dir, state)
            errors.extend(content_errors)
            warnings.extend(content_warnings)
        report["project"] = str(project_dir)

    if args.reference_memory:
        memory_path = Path(args.reference_memory)
        if not memory_path.is_file():
            errors.append(f"{memory_path}: 文件不存在")
        else:
            errors.extend(validate_file(memory_path, "reference-memory"))

    report["errors"] = list(errors)
    report["warnings"] = list(warnings)
    report["ok"] = not errors
    if args.json:
        _emit(report, True)
    else:
        if errors:
            _print("校验失败:")
            for error in errors:
                _print(f"- {error}")
        else:
            _print("校验通过")
        for warning in warnings:
            _print(f"[提示] {warning}")
    return EXIT_OK if not errors else EXIT_FAIL


def cmd_brand_guard(args: argparse.Namespace) -> int:
    try:
        report = brand_scan(repo_root=args.root, config_path=args.config)
    except BrandGuardError as exc:
        _print(f"品牌守卫无法运行: {exc}")
        return EXIT_ENV
    if args.json:
        _emit(report, True)
    else:
        hits = report["hits"]
        if hits:
            _print("命中禁用词（term#N 为词表序号，不输出明文）:")
            for hit in sorted(hits, key=lambda item: (item["path"], item["line"])):
                _print(f"- {hit['path']}:{hit['line']}  {hit['term']}")
        _print(
            f"扫描 {report['scanned']} 个文件；命中 {len(hits)} 处；"
            f"跳过 {len(report['skipped'])} 个；缺失目标 {len(report['missing_targets'])} 个"
        )
    return EXIT_OK if report["ok"] else EXIT_FAIL


def cmd_init(args: argparse.Namespace) -> int:
    try:
        report = create_project(
            args.name,
            base=args.project_root,
            entry=args.entry,
            mode=args.mode,
            force=args.force,
        )
    except ProjectError as exc:
        _print(str(exc))
        return EXIT_USAGE if "不能为空" in str(exc) else EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"已创建项目: {report['path']}")
        _print(
            f"入口 {report['entry']}；当前阶段 {report['stage']} {report['stage_name']}；"
            f"状态文件 00_project/state.json；参考记忆 00_project/reference-memory.json"
        )
        _print(f"项目根目录: {Path(report['path']).parent}")
        _print(
            "下一步：workbench.py check --project <路径> --content；"
            "gate list / gate pass；跨项目总览：workbench.py project list"
        )
        _print("如需固定项目位置：设置环境变量 AI_FILM_PROJECTS_ROOT 指向统一目录后重新 init。")
    return EXIT_OK


def cmd_route(args: argparse.Namespace) -> int:
    try:
        result = classify(args.text)
    except Exception as exc:  # noqa: BLE001 - 规则文件异常统一报环境错误
        _print(f"意图路由失败: {exc}")
        return EXIT_ENV
    if args.json:
        _emit(result, True)
    else:
        _print(f"意图: {result['kind']}" + (f"（{result['matched']}）" if result["matched"] else ""))
        for key in ("command", "stage", "entry", "note"):
            if result.get(key):
                _print(f"- {key}: {result[key]}")
        _print(f"- 维护口令隔离: {'是' if result['is_maintenance'] else '否'}")
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    project = Path(args.project)
    try:
        state = load_state(project)
        registry = load_registry()
    except (ProjectError, RegistryError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    ensure_stage_gates(state, state["stage"], registry)
    action = args.action
    try:
        if action == "list":
            detail = gate_detail(state, registry=registry)
            if args.json:
                _emit({"project": str(project), "stage": state["stage"], "gates": detail}, True)
            else:
                _print(f"项目 {state['project']}；阶段 {state['stage']}")
                for item in detail:
                    _print(
                        f"- [{item['status']}] {item['id']}（{item['type']}）"
                        f"{('：' + item['description']) if item['description'] else ''}"
                    )
            return EXIT_OK
        if not args.gate_id:
            _print("pass/fail/waive 需要指定门禁 id")
            return EXIT_USAGE
        if action == "pass":
            entry = pass_gate(state, args.gate_id, note=args.note, registry=registry)
        elif action == "fail":
            entry = fail_gate(state, args.gate_id, note=args.note, registry=registry)
        else:
            entry = waive_gate(state, args.gate_id, note=args.note, registry=registry)
    except GateError as exc:
        _print(str(exc))
        return EXIT_FAIL
    save_state(project, state)
    refresh_status_card(project, registry)
    payload = {"ok": True, "gate": entry, "stage": state["stage"], "project": str(project)}
    if args.json:
        _emit(payload, True)
    else:
        _print(f"门禁 {entry['id']} 已置为 {entry['status']}（阶段 {state['stage']}）")
    return EXIT_OK


def cmd_next(args: argparse.Namespace) -> int:
    project = Path(args.project)
    try:
        state = load_state(project)
        registry = load_registry()
    except (ProjectError, RegistryError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    ensure_stage_gates(state, state["stage"], registry)
    ok, reasons = can_advance(state, registry=registry)
    if not ok:
        payload = {"ok": False, "stage": state["stage"], "blocked": True, "reasons": reasons}
        if args.json:
            _emit(payload, True)
        else:
            _print(f"不能推进（阶段 {state['stage']}）:")
            for reason in reasons:
                _print(f"- {reason}")
        return EXIT_FAIL
    try:
        next_stage = advance(state, registry=registry)
    except GateError as exc:
        _print(str(exc))
        return EXIT_FAIL
    save_state(project, state)
    refresh_status_card(project, registry)
    payload = {
        "ok": True,
        "project": str(project),
        "stage": next_stage,
        "version": state["version"],
        "next_action": state["next_action"],
    }
    if args.json:
        _emit(payload, True)
    else:
        _print(f"已推进到阶段 {next_stage}（状态版本 {state['version']}）")
        _print(state["next_action"])
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        _print(f"文件不存在: {path}")
        return EXIT_FAIL
    try:
        errors = validate_file(path, args.schema)
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        _print(f"校验无法执行: {exc}")
        return EXIT_FAIL
    if errors:
        _print(f"{path} 对照 {args.schema} 校验失败:")
        for error in errors:
            _print(f"- {error}")
        return EXIT_FAIL
    _print(f"{path} 对照 {args.schema} 校验通过")
    return EXIT_OK


def cmd_install(args: argparse.Namespace) -> int:
    try:
        report = install_skills(
            args.source,
            target=args.target,
            backup_root=args.backup_dir,
            dry_run=args.dry_run,
        )
    except InstallerError as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        mode = "演练" if report.get("dry_run") else "安装"
        _print(f"Skill {mode}：{report['source']} -> {report['target']}")
        _print(f"- 共 {len(report['skills'])} 个：{', '.join(report['skills'])}")
        if not report.get("dry_run"):
            _print(f"- 已备份旧版本：{', '.join(report['backed_up']) or '无'}")
            _print(f"- 保留配置：{', '.join(report['preserved']) or '无'}")
            _print(f"- 备份目录：{report['backup']}")
    return EXIT_OK


def cmd_migrate(args: argparse.Namespace) -> int:
    try:
        report = migrate_project(args.project)
    except (MigrationError, ProjectError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"项目已迁移: {report['project']}")
        _print(f"- 状态：阶段 {report['stage']} / 入口 {report['entry']} / 参考条目 {report['reference_entries']}")
        _print(f"- 备份目录：{report['backup']}")
        _print(f"- 旧参考记忆：{report['legacy_memory_retired'] or '无'}")
    return EXIT_OK


def cmd_upgrade(args: argparse.Namespace) -> int:
    try:
        report = upgrade_project_rules(args.project)
    except (MigrationError, ProjectError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"项目规则已升级: {report['project']}")
        _print(f"- 备份目录：{report['backup']}")
        _print(f"- 备份文件：{', '.join(report['backed_up']) or '无'}")
    return EXIT_OK


def cmd_knowledge_probe(args: argparse.Namespace) -> int:
    service = KnowledgeService(args.kb_root)
    try:
        report = service.probe()
    except KnowledgeServiceError as exc:
        _print(f"知识库探测失败: {exc}")
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"知识库根: {report['kb_root']}")
        _print(f"索引文件: {report['db_path']}（{report['size_bytes']} 字节）")
        _print(
            f"schema: {report['schema']}；文档 {report['documents']} 份；"
            f"已索引 {report['indexed_documents']} 份；磁盘可读正文抽检 {report['content_files']} 份"
        )
        _print(f"外部 FTS 可用: {'是' if report['fts_external_supported'] else '否'}")
        _print(f"FTS 说明: {report['fts_note']}")
        for issue in report["issues"]:
            _print(f"[问题] {issue}")
    return EXIT_OK if not report["issues"] else EXIT_FAIL


def cmd_knowledge_search(args: argparse.Namespace) -> int:
    service = KnowledgeService(args.kb_root)
    try:
        result = service.search(
            project=args.project,
            stage=args.stage,
            problem=args.problem,
            queries=list(args.query),
            candidates_limit=args.candidates_limit,
            evidence_limit=args.evidence_limit,
            fallback=not args.no_fallback,
            fallback_max_files=args.fallback_files,
            fallback_max_bytes=args.fallback_bytes,
        )
    except KnowledgeServiceError as exc:
        _print(f"检索失败: {exc}")
        return EXIT_FAIL

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result["card"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        _emit(result, True)
    else:
        report = result["report"]
        _print(f"状态: {result['status']} — {report['statement']}")
        _print(
            f"候选 {report['candidates']} 条；文件级证据 {report['evidence']} 条；"
            f"缺失文件 {report['missing_files']} 条"
        )
        fallback = report.get("fallback") or {}
        if fallback.get("enabled"):
            trigger = fallback.get("trigger") or "未触发"
            _print(
                f"有限正文回退: 触发={trigger}；扫描 {fallback['files_scanned']} 份；"
                f"回退证据 {fallback['hits']} 条"
            )
        else:
            _print("有限正文回退: 已关闭")
        for item in result["card"]["evidence"]:
            _print(f"- {item['path']}（{item['page']}）命中「{item['hit']}」：{item['snippet'][:120]}")
        if args.out:
            _print(f"知识卡已写入: {args.out}（contracts v1.0）")
    return EXIT_OK


def _resolve_project(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    fallback = default_projects_root() / value
    return fallback if fallback.exists() else candidate


def cmd_reference_list(args: argparse.Namespace) -> int:
    try:
        root = _resolve_project(args.project)
        memory = load_memory(root)
    except (MemoryError, ProjectError) as exc:
        _print(f"参考记忆读取失败: {exc}")
        return EXIT_FAIL
    if args.stage:
        try:
            entries = entries_for_stage(memory, args.stage)
        except MemoryError as exc:
            _print(str(exc))
            return EXIT_FAIL
        payload = {
            "project": str(root),
            "stage": args.stage,
            "count": len(entries),
            "entries": [
                {
                    "id": entry.get("id"),
                    "source": entry.get("source"),
                    "method": entry.get("method"),
                    "scope": entry.get("scope"),
                }
                for entry in entries
            ],
        }
    else:
        payload = {"project": str(root), **summarize_memory(memory)}
    if args.json:
        _emit(payload, True)
    else:
        if args.stage:
            _print(f"阶段 {args.stage} 启用的参考方法：{payload['count']} 条")
            for item in payload["entries"]:
                _print(f"- {item['id']}  {item['source']}  →  {item['method'][:60]}")
        else:
            _print(
                f"参考记忆：共 {payload['total']} 条，启用 {payload['enabled']}，"
                f"停用 {payload['disabled']}，移除 {payload['removed']}"
            )
            for scope, count in sorted(payload["by_scope"].items()):
                _print(f"- {scope}: {count}")
    return EXIT_OK


def _style_service() -> StyleService:
    return StyleService()


def cmd_style_list(args: argparse.Namespace) -> int:
    try:
        service = _style_service()
        entries = service.list(category=args.category, quality=args.quality)
    except StyleServiceError as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit({"count": len(entries), "entries": entries}, True)
    else:
        summary = service.status()
        _print(f"风格注册表：{summary['directors']} 条 / {summary['categories']} 类")
        for item in entries:
            issue_note = ""
            if item.get("issues"):
                labels = item.get("issue_labels") or []
                issue_note = "；待核：" + "、".join(labels[:2]) + ("…" if len(labels) > 2 else "")
            _print(
                f"- {item['id']}  {item['name_zh'] or item['name_en']}"
                f"（分类 {item['category']}，等级 {item['quality']}，待核问题 {item['issues']}{issue_note}）"
            )
        _print(f"共 {len(entries)} 条")
        grade_counts = summary.get("grade_counts") or {}
        if grade_counts and not args.quality:
            _print(
                "质量分级："
                + "；".join(f"{key} {grade_counts.get(key, 0)} 条" for key in ("A", "B", "C"))
            )
            if any(item.get("quality") != "A" for item in entries):
                _print("提示：非 A 级条目存在待核元数据（如图链/目录命名），结构校验不受影响，建议生成前抽查。")
    return EXIT_OK


def cmd_style_show(args: argparse.Namespace) -> int:
    try:
        profile = _style_service().build(args.ref, args.tool)
    except (StyleServiceError, AdapterError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(profile, True)
        return EXIT_OK
    _print(f"{profile['name']}（编号 {profile['director_no']}，分类 {profile['category']}，等级 {profile['quality']}）")
    try:
        entry = _style_service().get(args.ref)
    except StyleServiceError:
        entry = {}
    issues = entry.get("issues") or []
    if (entry.get("quality") and entry.get("quality") != "A") or issues:
        _print(
            f"质量提示：{entry.get('quality', profile['quality'])} 级"
            + (f"，待核问题 {len(issues)} 条：" + "；".join(str(item) for item in issues[:3]) if issues else "，元数据完整")
        )
    _print(f"标签: {'、'.join(profile['tags'])}")
    _print("调色板:")
    for item in profile["palette"]:
        _print(f"- {item['name']}  {item['hex']}  {item['ratio']:g}%")
    _print(f"光线: {profile['lighting']}")
    _print(f"构图/镜头: {profile['lens']}")
    if profile["materials"]:
        _print(f"材质与色彩: {'、'.join(profile['materials'])}")
    if profile["negatives"]:
        _print(f"禁止/避免: {'；'.join(profile['negatives'])}")
    if args.tool:
        from style_service import normalize_tool

        canonical = normalize_tool(args.tool)
        _print(f"工具适配[{canonical}]: {profile['tool_adapters'].get(canonical, '')}")
    return EXIT_OK


def cmd_style_resolve(args: argparse.Namespace) -> int:
    try:
        entry = _style_service().get(args.ref)
    except StyleServiceError as exc:
        _print(str(exc))
        return EXIT_FAIL
    summary = {
        "id": entry.get("id"),
        "name_en": entry.get("name_en", ""),
        "name_zh": entry.get("name_zh", ""),
        "category": entry.get("category", ""),
        "category_name": entry.get("category_name", ""),
        "quality": entry.get("quality", ""),
        "issues": entry.get("issues", []),
        "references_count": entry.get("references_count", 0),
        "prompts": entry.get("prompts", {}),
        "directory": entry.get("directory", ""),
    }
    if args.json:
        _emit(summary, True)
    else:
        _print(f"{summary['id']}  {summary['name_zh']} / {summary['name_en']}")
        _print(f"分类 {summary['category']}；等级 {summary['quality']}；目录 {summary['directory']}")
        _print(f"提示词行数: {summary['prompts']}")
        if summary["issues"]:
            _print(f"待核问题: {'；'.join(summary['issues'])}")
    return EXIT_OK


def cmd_style_validate(args: argparse.Namespace) -> int:
    if not args.file and not args.text:
        _print("需要 --file 或 --text")
        return EXIT_USAGE
    try:
        body = (
            Path(args.file).read_text(encoding="utf-8-sig")
            if args.file
            else str(args.text)
        )
    except OSError as exc:
        _print(f"读取提示词失败: {exc}")
        return EXIT_ENV
    try:
        issues = validate_prompt(args.tool, body)
    except AdapterError as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit({"tool": args.tool, "ok": not issues, "issues": issues}, True)
    else:
        if issues:
            _print("结构校验未通过:")
            for issue in issues:
                _print(f"- {issue}")
        else:
            _print("结构校验通过（v1）")
    return EXIT_OK if not issues else EXIT_FAIL


def cmd_style_apply(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    try:
        report = _style_service().apply(project, args.ref, args.tool)
    except (StyleServiceError, AdapterError, ProjectError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"风格卡已写入: {report['card']}")
        _print(f"项目 {project}；风格 {report['style_id']}；状态 {report['state']['status']}")
        _print(f"下一步: style inject {report['style_id']} --project <项目> --stage 06|08 --tool <工具> --prompt-file <文件>")
    return EXIT_OK


def cmd_style_inject(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    try:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig")
    except OSError as exc:
        _print(f"读取提示词失败: {exc}")
        return EXIT_ENV
    try:
        report = _style_service().inject(project, args.ref, args.stage, args.tool, prompt)
    except (StyleServiceError, AdapterError, ProjectError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"阶段 {report['stage']} / 工具 {report['tool']}；注入记录: {report['record']}")
        _print("—" * 40)
        _print(report["combined_prompt"])
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    out = Path(args.out) if args.out else None
    try:
        report = export_project(project, out, overwrite=args.force)
    except (ProjectError, OSError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"已导出: {report['archive']}")
        _print(
            f"项目 {report['project']}；版本 {report['state_version']}；"
            f"阶段 {report['stage']}；{report['files']} 个文件 / {report['bytes']} 字节"
        )
    return EXIT_OK


def cmd_restore(args: argparse.Namespace) -> int:
    dest = Path(args.dest).expanduser() if args.dest else default_projects_root()
    try:
        report = restore_project(args.archive, dest)
    except (ProjectError, OSError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(f"已还原: {report['path']}")
        _print(
            f"项目 {report['project']}；版本 {report['state_version']}；"
            f"阶段 {report['stage']}；{report['files']} 个文件"
        )
    return EXIT_OK


def cmd_artifact_register(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    try:
        report = register_artifacts(
            project,
            args.stage,
            args.kind,
            list(args.path),
            note=args.note,
            next_action=args.next_action,
        )
    except ProjectError as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(
            f"已登记阶段 {report['stage']}：{report['kind']}（{len(report['files'])} 个文件）"
        )
        for item in report["files"]:
            _print(f"- {item['path']}  {item['bytes']} 字节  sha256={item['sha256'][:16]}")
        if report["missing"]:
            _print("[提示] 未找到: " + "；".join(report["missing"]))
        _print(f"状态文件: {report['state_file']}")
    return EXIT_OK


def cmd_knowledge_bridge(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    references = [item.strip() for item in args.references.split(",") if item.strip()] if args.references else None
    try:
        report = update_knowledge_bridge(
            project,
            args.status,
            last_card=args.card,
            confirmed_references=references,
            note=args.note,
        )
    except ProjectError as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        bridge = report["knowledge_bridge"]
        _print(f"知识桥状态: {bridge.get('status')}")
        if bridge.get("last_card"):
            _print(f"- 知识卡: {bridge['last_card']}")
        if bridge.get("confirmed_references"):
            _print(f"- 已确认参考: {', '.join(bridge['confirmed_references'])}")
        _print(f"状态文件: {report['state_file']}")
    return EXIT_OK


def cmd_style_inject_batch(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    try:
        payload = json.loads(Path(args.batch).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        _print(f"读取批量文件失败: {exc}")
        return EXIT_ENV
    if not isinstance(payload, dict):
        _print("批量文件必须是 JSON 对象")
        return EXIT_USAGE
    stage = str(payload.get("stage") or args.stage)
    tool = str(payload.get("tool") or args.tool)
    items = payload.get("items")
    try:
        report = _style_service().inject_batch(
            project,
            stage,
            tool,
            items if isinstance(items, list) else [],
            args.out_dir,
            per_shot_records=args.per_shot_records,
        )
    except (StyleServiceError, AdapterError, ProjectError) as exc:
        _print(str(exc))
        return EXIT_FAIL
    if args.json:
        _emit(report, True)
    else:
        _print(
            f"阶段 {report['stage']} / 工具 {report['tool']}：批量注入 {report['count']} 条"
        )
        _print(f"批量记录: {report['record']}")
        for item in report["items"]:
            _print(f"- {item['shot']}  sha256={item['prompt_sha256'][:16]}  {item['chars']} 字")
        if report["written"]:
            _print(f"组合提示词: {len(report['written'])} 个文件 → {Path(report['written'][0]).parent}")
        if report.get("shot_records"):
            _print(
                f"逐镜记录: {len(report['shot_records'])} 份 → "
                f"{Path(report['shot_records'][0]).parent}"
            )
    return EXIT_OK


def cmd_project_list(args: argparse.Namespace) -> int:
    if args.root:
        roots = [Path(item).expanduser() for item in args.root]
    else:
        roots = [default_projects_root()]
        repo_sibling = WORKBENCH_ROOT.parent / "projects"
        if repo_sibling != roots[0]:
            roots.append(repo_sibling)
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    seen_paths: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            state_file = child / "00_project" / "state.json"
            if not child.is_dir() or not state_file.is_file():
                continue
            resolved = child.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                state = load_state(child)
            except ProjectError as exc:
                problems.append(f"{child.name}: {exc}")
                continue
            revision = state.get("revision_log") or []
            if revision and revision[-1].get("at"):
                updated = str(revision[-1]["at"])
            else:
                updated = datetime.fromtimestamp(state_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            stats = None
            if getattr(args, "stats", False):
                gate_rows = [item for item in (state.get("gates") or []) if isinstance(item, dict)]
                try:
                    graph_rows = list_graphs(child)
                except Exception:  # noqa: BLE001 - 统计失败不影响列表
                    graph_rows = []
                try:
                    run_rows = list_runs(child, limit=200)
                except Exception:  # noqa: BLE001
                    run_rows = []
                last_run = None
                if run_rows:
                    last_run = {
                        "status": run_rows[0].get("status"),
                        "at": run_rows[0].get("started_at") or run_rows[0].get("finished_at") or "",
                    }
                stats = {
                    "artifacts": len(state.get("stage_artifacts") or {}),
                    "pending_gates": sum(
                        1 for item in gate_rows if item.get("status") == "pending"
                    ),
                    "workflows": len(graph_rows),
                    "runs": len(run_rows),
                    "last_run": last_run,
                }
            rows.append(
                {
                    "name": child.name,
                    "project": state.get("project", child.name),
                    "entry": state.get("entry", ""),
                    "stage": state.get("stage", ""),
                    "version": state.get("version", ""),
                    "mode": state.get("mode", ""),
                    "style": (state.get("style") or {}).get("status", "off"),
                    "knowledge": (state.get("knowledge_bridge") or {}).get("status", "off"),
                    "updated": updated,
                    "path": str(child),
                    "root": str(root),
                    **(stats or {}),
                }
            )
    rows.sort(key=lambda item: item["updated"], reverse=True)
    payload = {
        "root": str(roots[0]),
        "roots": [str(root) for root in roots],
        "count": len(rows),
        "projects": rows,
        "problems": problems,
    }
    if args.json:
        _emit(payload, True)
    else:
        _print(f"项目根目录: {'；'.join(payload['roots'])}（{len(rows)} 个项目）")
        for item in rows:
            line = (
                f"- {item['name']}  阶段 {item['stage']}  {item['version']}  入口 {item['entry']}"
                f"  风格 {item['style']}  知识桥 {item['knowledge']}  更新 {item['updated']}"
            )
            if "workflows" in item:
                line += (
                    f"  产物 {item['artifacts']} · 待门禁 {item['pending_gates']}"
                    f" · 流程 {item['workflows']} · 运行 {item['runs']}"
                )
            _print(line)
        for problem in problems:
            _print(f"  [跳过] {problem}")
    return EXIT_OK


def _flow_read(args: argparse.Namespace) -> dict[str, Any]:
    """按 --file 或 --project + --graph 读取流程图 JSON。"""
    if getattr(args, "file", None):
        path = Path(args.file)
        if not path.is_file():
            raise FlowError(f"流程图文件不存在: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FlowError(f"流程图读取失败: {exc}") from exc
    if args.project and getattr(args, "graph", None):
        project = resolve_project(args.project)
        return read_graph_data(project, args.graph)
    raise FlowError("需要 --file，或同时提供 --project 与 --graph")


def cmd_flow_new(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        graph_id = args.graph or graph_id_from_name(args.name)
        template_id = getattr(args, "template", None)
        if template_id:
            data = instantiate_template(template_id, project.name, graph_id=graph_id, name=args.name)
        else:
            data = default_graph(project.name, graph_id=graph_id)
            data["name"] = args.name
            data["nodes"][0]["params"]["project"] = project.name
        target = project / "00_project" / "workflows" / f"{graph_id}.json"
        if target.is_file() and not args.force:
            _print(f"流程图已存在: {target}（如需覆盖请加 --force）")
            return EXIT_FAIL
        write_graph_data(project, data)
        payload = {"ok": True, "project": str(project), "graph_id": graph_id, "file": str(target)}
        _emit(payload, args.json)
        if not args.json:
            _print(f"已创建流程图: {graph_id}（{args.name}）")
            _print(f"文件: {target}")
            _print("下一步: 编辑后运行 `workbench.py flow serve --project " + str(project) + "` 在浏览器中拖拽连线。")
        return EXIT_OK
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL


def cmd_flow_list(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        items = list_graphs(project)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    if args.json:
        _emit({"ok": True, "project": str(project), "count": len(items), "graphs": items}, True)
        return EXIT_OK
    _print(f"项目: {project}")
    _print(f"流程图: {len(items)} 个")
    for item in items:
        _print(
            f"- {item['graph_id']}  {item['name']}  "
            f"节点 {item['nodes']} / 连线 {item['edges']}  更新 {item['updated_at']}"
        )
    return EXIT_OK


def cmd_flow_show(args: argparse.Namespace) -> int:
    try:
        data = _flow_read(args)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    _print(json.dumps(data, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_flow_validate(args: argparse.Namespace) -> int:
    try:
        data = _flow_read(args)
        result = validate_graph(data, load_node_types())
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    payload = {"ok": result["ok"], "graph_id": data.get("graph_id"), **result}
    if args.json:
        _emit(payload, True)
    else:
        _print(f"流程图: {data.get('graph_id')}（节点 {len(data.get('nodes') or [])} / 连线 {len(data.get('edges') or [])}）")
        if result["errors"]:
            for item in result["errors"]:
                _print(f"[错误] {item}")
        if result["warnings"]:
            for item in result["warnings"]:
                _print(f"[提示] {item}")
        _print("校验通过" if result["ok"] else "校验失败")
    return EXIT_OK if result["ok"] else EXIT_FAIL


def cmd_flow_run(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        data = read_graph_data(project, args.graph)
        retries = getattr(args, "retries", None)
        if retries is not None:
            data = dict(data)
            settings = dict(data.get("settings") or {})
            settings["node_retries"] = max(0, min(3, int(retries)))
            data["settings"] = settings
        runner = Runner(
            project,
            data,
            dry_run=args.dry_run,
            auto_confirm=args.yes,
        )
        result = runner.run(mode=args.mode, target=args.node)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    run = result["run"]
    if args.json:
        _emit(result, True)
    else:
        _print(f"运行 {run['run_id']}：{run['status']}（模式 {run['mode']}，dry_run={run['dry_run']}）")
        for step in run.get("steps") or []:
            flag = "OK" if step.get("status") in {"succeeded", "planned"} else step.get("status", "").upper()
            line = f"[{flag}] {step['node_id']}"
            if step.get("outputs"):
                line += "  " + "；".join(str(x) for x in step["outputs"])
            if step.get("error"):
                line += "  错误: " + step["error"]
            _print(line)
        if result.get("awaiting"):
            awaiting = result["awaiting"]
            _print("")
            _print(f"等待人工确认: {awaiting.get('prompt')}（节点 {awaiting.get('node_id')}）")
            _print("提示: 浏览器端 `flow serve` 可确认；或加 --yes 自动确认。")
        _print("运行记录: " + str(project / "00_project" / "workflows" / "runs" / (run["run_id"] + ".json")))
    return EXIT_OK if run.get("status") in {"succeeded", "awaiting_confirm"} else EXIT_FAIL


def cmd_flow_templates(args: argparse.Namespace) -> int:
    try:
        templates = load_templates()
    except Exception as exc:  # TemplateError
        _print(f"错误: {exc}")
        return EXIT_FAIL
    if args.json:
        _emit({"ok": True, "count": len(templates), "templates": templates}, True)
        return EXIT_OK
    _print(f"预置模板: {len(templates)} 个")
    for item in templates:
        graph = item.get("graph") or {}
        _print(f"- {item['template_id']}  {item['name']}（节点 {len(graph.get('nodes') or [])} / 连线 {len(graph.get('edges') or [])}）")
        _print(f"  {item['description']}")
    return EXIT_OK


def cmd_flow_runs(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        runs = list_runs(project, limit=args.limit)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    if args.json:
        _emit({"ok": True, "project": str(project), "count": len(runs), "runs": runs}, True)
        return EXIT_OK
    _print(f"项目: {project}")
    _print(f"运行历史: {len(runs)} 条")
    for run in runs:
        line = f"- {run['run_id']}  {run['status']}  {run['mode']}"
        if run.get("dry_run"):
            line += "  dry-run"
        line += f"  步骤 {run['steps']}"
        if run.get("failed"):
            line += f"  失败 {run['failed']}"
        if run.get("recovered_from"):
            line += f"  恢复自 {run['recovered_from']}"
        _print(line)
        if run.get("error"):
            _print(f"  错误: {run['error']}")
    return EXIT_OK


def cmd_flow_recover(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        result = recover_run(project, args.run, restore_state=args.restore_state, auto_confirm=args.yes)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    run = result["run"]
    if args.json:
        _emit(result, True)
        return EXIT_OK if run.get("status") in {"succeeded", "awaiting_confirm"} else EXIT_FAIL
    _print(
        f"恢复运行 {run['run_id']}（来自 {args.run}）：{run['status']}"
        + ("，已回滚状态快照" if result.get("state_restored") else "")
    )
    for step in run.get("steps") or []:
        flag = "OK" if step.get("status") in {"succeeded", "planned"} else step.get("status", "").upper()
        line = f"[{flag}] {step['node_id']}"
        if step.get("outputs"):
            line += "  " + "；".join(str(x) for x in step["outputs"])
        if step.get("error"):
            line += "  错误: " + step["error"]
        _print(line)
    return EXIT_OK if run.get("status") in {"succeeded", "awaiting_confirm"} else EXIT_FAIL


def cmd_flow_batch(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        if args.all:
            graph_ids = [item["graph_id"] for item in list_graphs(project)]
        else:
            graph_ids = [item.strip() for item in (args.graphs or "").split(",") if item.strip()]
        if not graph_ids:
            _print("错误: 请用 --graphs a,b 指定流程图，或使用 --all")
            return EXIT_USAGE
        results: list[dict[str, Any]] = []
        for graph_id in graph_ids:
            try:
                data = read_graph_data(project, graph_id)
                runner = Runner(project, data, dry_run=args.dry_run, auto_confirm=args.yes)
                result = runner.run(mode="full")
                run = result["run"]
                results.append(
                    {
                        "graph_id": graph_id,
                        "ok": run.get("status") in {"succeeded", "awaiting_confirm"},
                        "status": run.get("status"),
                        "run_id": run.get("run_id"),
                        "steps": len(run.get("steps") or []),
                        "error": next(
                            (step.get("error") for step in run.get("steps") or [] if step.get("error")),
                            None,
                        ),
                    }
                )
            except FlowError as exc:
                results.append({"graph_id": graph_id, "ok": False, "status": "error", "error": str(exc)})
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    ok = all(item.get("ok") for item in results)
    payload = {"ok": ok, "project": str(project), "count": len(results), "results": results}
    if args.json:
        _emit(payload, True)
    else:
        _print(f"批量运行: {len(results)} 个流程图")
        for item in results:
            line = f"- {item['graph_id']}  {item.get('status')}"
            if item.get("run_id"):
                line += f"  运行 {item['run_id']}"
            if item.get("error"):
                line += f"  错误: {item['error']}"
            _print(line)
        _print("全部成功" if ok else "存在失败，请查看运行记录")
    return EXIT_OK if ok else EXIT_FAIL


def cmd_flow_replay(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        run = read_run(project, args.run)
        graph = None
        graph_id = str(run.get("graph_id") or "")
        if graph_id:
            try:
                graph = read_graph_data(project, graph_id)
            except FlowError:
                graph = None
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    replay = build_replay(run, graph)
    if args.json:
        _emit({"ok": True, "project": str(project), "replay": replay}, True)
    else:
        _print(format_replay_text(replay))
    return EXIT_OK


def cmd_flow_export(args: argparse.Namespace) -> int:
    try:
        data = _flow_read(args)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    out = getattr(args, "out", None)
    if not out:
        _print(text)
        return EXIT_OK
    path = Path(out)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        _print(f"写入失败: {exc}")
        return EXIT_ENV
    _print(f"已导出流程图 {data.get('graph_id')} → {path}")
    return EXIT_OK


def cmd_flow_import(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        source = Path(args.file)
        if not source.is_file():
            raise FlowError(f"导入文件不存在: {source}")
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FlowError(f"导入文件读取失败: {exc}") from exc
        if not isinstance(data, dict):
            raise FlowError("导入文件必须是流程图 JSON 对象")
        result = validate_graph(data, load_node_types())
        if not result["ok"]:
            _print("流程图校验失败：")
            for item in result["errors"]:
                _print(f"- {item}")
            return EXIT_FAIL
        graph_id = str(getattr(args, "graph", None) or data.get("graph_id") or "").strip()
        if not graph_id:
            raise FlowError("导入文件缺少 graph_id，请用 --graph 指定")
        data["graph_id"] = graph_id
        data["project"] = project.name
        data["name"] = str(data.get("name") or graph_id)
        target = project / "00_project" / "workflows" / f"{graph_id}.json"
        if target.is_file() and not args.force:
            _print(f"错误: 流程图已存在: {graph_id}（使用 --force 覆盖）")
            return EXIT_FAIL
        write_graph_data(project, data)
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    payload = {
        "ok": True,
        "project": str(project),
        "graph_id": graph_id,
        "name": data.get("name"),
        "nodes": len(data.get("nodes") or []),
        "edges": len(data.get("edges") or []),
        "path": str(target),
    }
    if args.json:
        _emit(payload, True)
    else:
        _print(f"已导入流程图 {graph_id}（{payload['nodes']} 节点 / {payload['edges']} 连线）→ {target}")
    return EXIT_OK


def cmd_project_summary(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
    except FlowError as exc:
        print(f"错误: {exc}")
        return EXIT_FAILURE
    state = load_state(project)
    artifacts = []
    for stage, summary in (state.get("stage_artifacts") or {}).items():
        files = []
        for token in re.findall(r"[0-9A-Za-z_\u4e00-\u9fff./\-]+\.(?:md|json|txt)", str(summary)):
            path = project / token
            if path.exists():
                files.append({"path": token, "size": path.stat().st_size})
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
    payload = {
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
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"项目 {payload['project']}（阶段 {payload['stage']} / "
            f"{payload['version']} / 入口 {payload['entry']}）"
        )
        print(f"路径: {payload['path']}")
        print(f"产物 {len(artifacts)} 组 · 流程图 {len(graphs)} 个 · 运行 {len(runs)} 条")
        for item in artifacts:
            print(f"- [{item['stage']}] {item['summary']}")
        for graph in graphs:
            print(
                f"- 图 {graph['graph_id']} {graph.get('name') or ''}"
                f"（{len(graph['nodes'])} 节点 / {len(graph['edges'])} 连线）"
            )
    return EXIT_OK


def cmd_flow_diff(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        base = read_run(project, args.run)
        target = read_run(project, args.other_run)
        diff = compare_runs(base, target)
    except FlowError as exc:
        print(f"错误: {exc}")
        return EXIT_FAILURE
    if args.json:
        print(json.dumps({"ok": True, "project": str(project), "diff": diff}, ensure_ascii=False, indent=2))
    else:
        print(format_compare_text(diff))
    return EXIT_OK


def cmd_flow_serve(args: argparse.Namespace) -> int:
    try:
        project = resolve_project(args.project)
        from webui import serve_forever
    except FlowError as exc:
        _print(f"错误: {exc}")
        return EXIT_FAIL
    try:
        serve_forever(project, host=args.host, port=args.port, use_token=not args.no_token)
    except OSError as exc:
        _print(f"启动失败: {exc}")
        return EXIT_ENV
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workbench",
        description="AI 影视工作台：阶段契约、路由与品牌守卫。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="显示版本")
    version.set_defaults(func=cmd_version)

    doctor = sub.add_parser("doctor", help="环境与仓库自检")
    doctor.add_argument("--json", action="store_true", help="以 JSON 输出")
    doctor.set_defaults(func=cmd_doctor)

    check = sub.add_parser("check", help="校验注册表与项目状态")
    check.add_argument("--registry", help="阶段注册表路径（默认仓库内）")
    check.add_argument("--project", help="项目目录（读取 00_project/state.json）")
    check.add_argument("--reference-memory", help="reference-memory JSON 路径")
    check.add_argument("--content", action="store_true", help="内容一致性检查（风格/知识桥/产物/时长）")
    check.add_argument("--json", action="store_true", help="以 JSON 输出")
    check.set_defaults(func=cmd_check)

    guard = sub.add_parser("brand-guard", help="扫描禁用词")
    guard.add_argument("--root", help="工作区根目录（默认仓库所在工作区）")
    guard.add_argument("--config", help="品牌守卫配置路径")
    guard.add_argument("--json", action="store_true", help="以 JSON 输出")
    guard.set_defaults(func=cmd_brand_guard)

    init = sub.add_parser("init", help="创建项目骨架（状态卡 v2）")
    init.add_argument("name", help="项目名称")
    init.add_argument("--project-root", help="项目根目录（默认文档目录下的工作台 projects/）")
    init.add_argument("--entry", default="A", choices=["A", "B", "C", "D"], help="项目入口")
    init.add_argument("--mode", default="full",
                      choices=["full", "stage", "relay", "revise"], help="运行模式")
    init.add_argument("--force", action="store_true", help="目标存在时覆盖")
    init.add_argument("--json", action="store_true", help="以 JSON 输出")
    init.set_defaults(func=cmd_init)

    project = sub.add_parser("project", help="跨项目总览")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_list = project_sub.add_parser("list", help="列出项目根目录下的项目状态")
    project_list.add_argument(
        "--root", action="append",
        help="项目根目录（可多次传入；缺省扫描默认项目根与仓库同级 projects/）",
    )
    project_list.add_argument("--json", action="store_true", help="以 JSON 输出")
    project_list.add_argument("--stats", action="store_true", help="附带流程/运行/产物统计")
    project_summary = project_sub.add_parser("summary", help="查看项目产物与流程图摘要")
    project_summary.add_argument("--project", required=True, help="项目名或项目路径")
    project_summary.add_argument("--json", action="store_true", help="以 JSON 输出")
    project_summary.set_defaults(func=cmd_project_summary)
    project_list.set_defaults(func=cmd_project_list)

    route = sub.add_parser("route", help="意图路由：维护口令 / 知识库 / 阶段 / 入口 / 修订")
    route.add_argument("text", help="用户输入文本")
    route.add_argument("--json", action="store_true", help="以 JSON 输出")
    route.set_defaults(func=cmd_route)

    gate = sub.add_parser("gate", help="门禁查看与状态变更")
    gate.add_argument("action", nargs="?", default="list",
                      choices=["list", "pass", "fail", "waive"], help="动作（默认 list）")
    gate.add_argument("gate_id", nargs="?", help="门禁 id")
    gate.add_argument("--project", required=True, help="项目目录")
    gate.add_argument("--note", default="", help="备注")
    gate.add_argument("--json", action="store_true", help="以 JSON 输出")
    gate.set_defaults(func=cmd_gate)

    nxt = sub.add_parser("next", help="推进到下一阶段（门禁未通过会被拒绝）")
    nxt.add_argument("--project", required=True, help="项目目录")
    nxt.add_argument("--json", action="store_true", help="以 JSON 输出")
    nxt.set_defaults(func=cmd_next)

    install = sub.add_parser("install", help="安装/升级 Skill（备份+回滚+配置保留）")
    install.add_argument("--source", required=True, help="包含 <skill>/SKILL.md 的源目录")
    install.add_argument("--target", help="目标 Skill 目录（默认 ~/.codex/skills）")
    install.add_argument("--backup-dir", help="备份根目录（默认目标同级）")
    install.add_argument("--dry-run", action="store_true", help="只演练不写入")
    install.add_argument("--json", action="store_true", help="以 JSON 输出")
    install.set_defaults(func=cmd_install)

    migrate = sub.add_parser("migrate", help="旧项目迁移：状态卡 v2 + 参考记忆 JSON")
    migrate.add_argument("--project", required=True, help="项目目录")
    migrate.add_argument("--json", action="store_true", help="以 JSON 输出")
    migrate.set_defaults(func=cmd_migrate)

    upgrade = sub.add_parser("upgrade", help="旧项目规则升级（备份、补齐目录、更新规则文件）")
    upgrade.add_argument("--project", required=True, help="项目目录")
    upgrade.add_argument("--json", action="store_true", help="以 JSON 输出")
    upgrade.set_defaults(func=cmd_upgrade)

    export_cmd = sub.add_parser("export", help="导出项目为可迁移 ZIP（含元数据）")
    export_cmd.add_argument("--project", required=True, help="项目名或项目路径")
    export_cmd.add_argument("--out", help="ZIP 输出路径（缺省 00_project/history/project-<版本>-<时间>.zip）")
    export_cmd.add_argument("--force", action="store_true", help="允许覆盖已存在的 ZIP")
    export_cmd.add_argument("--json", action="store_true", help="以 JSON 输出")
    export_cmd.set_defaults(func=cmd_export)

    restore_cmd = sub.add_parser("restore", help="从 ZIP 还原项目（拒绝路径穿越与非空覆盖）")
    restore_cmd.add_argument("archive", help="导出的 ZIP 路径")
    restore_cmd.add_argument("--dest", help="还原目标根目录（缺省项目默认根目录）")
    restore_cmd.add_argument("--json", action="store_true", help="以 JSON 输出")
    restore_cmd.set_defaults(func=cmd_restore)

    artifact = sub.add_parser("artifact", help="阶段产物登记（写 state.stage_artifacts 与 revision_log）")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_register = artifact_sub.add_parser("register", help="登记阶段产物文件（支持 glob）")
    artifact_register.add_argument("--project", required=True, help="项目名或项目路径")
    artifact_register.add_argument(
        "--stage", required=True,
        choices=[f"0{index}" for index in range(1, 9)] + ["done"], help="阶段 01-08 或 done",
    )
    artifact_register.add_argument("--kind", required=True, help="产物类型（如 剧本/镜头规划/提示词）")
    artifact_register.add_argument(
        "--path", action="append", required=True, help="项目内相对路径或 glob（可多次传入）"
    )
    artifact_register.add_argument("--note", default="", help="revision_log 备注")
    artifact_register.add_argument("--next-action", help="覆盖 state.next_action")
    artifact_register.add_argument("--json", action="store_true", help="以 JSON 输出")
    artifact_register.set_defaults(func=cmd_artifact_register)

    validate_cmd = sub.add_parser("validate", help="校验任意 JSON 文件")
    validate_cmd.add_argument("path", help="JSON 文件路径")
    validate_cmd.add_argument("--schema", required=True, help="schema 名称（如 state.schema.json）")
    validate_cmd.set_defaults(func=cmd_validate)

    knowledge = sub.add_parser("knowledge", help="知识服务：只读检索与证据卡")
    knowledge_sub = knowledge.add_subparsers(dest="knowledge_command", required=True)

    knowledge_probe = knowledge_sub.add_parser("probe", help="探测知识库索引指纹与可复用能力")
    knowledge_probe.add_argument("--kb-root", help="知识库根目录（含 knowledgeIndex.sqlite）")
    knowledge_probe.add_argument("--json", action="store_true", help="以 JSON 输出")
    knowledge_probe.set_defaults(func=cmd_knowledge_probe)

    knowledge_search = knowledge_sub.add_parser("search", help="检索并生成 knowledge-card")
    knowledge_search.add_argument("--project", required=True, help="项目名")
    knowledge_search.add_argument(
        "--stage", required=True, choices=[f"0{index}" for index in range(1, 9)], help="阶段 01-08"
    )
    knowledge_search.add_argument("--problem", required=True, help="需要解决的明确问题")
    knowledge_search.add_argument(
        "--query",
        action="append",
        required=True,
        help='格式 "lane:查询词"；lane=screenplay/method_book/cultural_fact/style_reference',
    )
    knowledge_search.add_argument("--kb-root", help="知识库根目录（缺省自动探测）")
    knowledge_search.add_argument("--out", help="知识卡 JSON 输出路径")
    knowledge_search.add_argument("--candidates-limit", type=int, default=40)
    knowledge_search.add_argument("--evidence-limit", type=int, default=8)
    knowledge_search.add_argument(
        "--no-fallback", action="store_true", help="关闭有限正文回退扫描（默认开启）"
    )
    knowledge_search.add_argument(
        "--fallback-files", type=int, default=200, help="回退扫描文件数上限（默认 200）"
    )
    knowledge_search.add_argument(
        "--fallback-bytes", type=int, default=262144, help="回退单文件读取字节上限（默认 256KB）"
    )
    knowledge_search.add_argument("--json", action="store_true", help="以 JSON 输出")
    knowledge_search.set_defaults(func=cmd_knowledge_search)

    knowledge_bridge = knowledge_sub.add_parser("bridge", help="更新项目知识桥状态（off/requested/on）")
    knowledge_bridge.add_argument("--project", required=True, help="项目名或项目路径")
    knowledge_bridge.add_argument("--status", required=True, choices=["off", "requested", "on"])
    knowledge_bridge.add_argument("--card", help="知识卡项目内相对路径")
    knowledge_bridge.add_argument("--references", help="已确认参考方法编号，逗号分隔")
    knowledge_bridge.add_argument("--note", default="", help="备注")
    knowledge_bridge.add_argument("--json", action="store_true", help="以 JSON 输出")
    knowledge_bridge.set_defaults(func=cmd_knowledge_bridge)

    reference = sub.add_parser("reference", help="跨阶段参考记忆：统计与按阶段加载")
    reference_sub = reference.add_subparsers(dest="reference_command", required=True)

    reference_list = reference_sub.add_parser("list", help="列出启用的参考方法（可指定阶段）")
    reference_list.add_argument("--project", required=True, help="项目名或项目路径")
    reference_list.add_argument(
        "--stage", choices=[f"0{index}" for index in range(1, 9)], help="只看该阶段适用的条目"
    )
    reference_list.add_argument("--json", action="store_true", help="以 JSON 输出")
    reference_list.set_defaults(func=cmd_reference_list)

    style = sub.add_parser("style", help="风格服务：注册表 / 风格卡 / 结构校验 / 06-08 注入")
    style_sub = style.add_subparsers(dest="style_command", required=True)

    style_list = style_sub.add_parser("list", help="列出风格注册表条目")
    style_list.add_argument("--category", help="按分类编号过滤（如 01）")
    style_list.add_argument("--quality", choices=["A", "B", "C"], help="按等级过滤")
    style_list.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_list.set_defaults(func=cmd_style_list)

    style_show = style_sub.add_parser("show", help="查看某个导演的风格卡（不写项目）")
    style_show.add_argument("ref", help="编号 / 英文名 / 中文名")
    style_show.add_argument("--tool", help="只显示某工具的适配文本")
    style_show.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_show.set_defaults(func=cmd_style_show)

    style_resolve = style_sub.add_parser("resolve", help="解析风格编号或名称")
    style_resolve.add_argument("ref", help="编号 / 英文名 / 中文名")
    style_resolve.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_resolve.set_defaults(func=cmd_style_resolve)

    style_validate = style_sub.add_parser("validate", help="按 v1 规范校验提示词结构")
    style_validate.add_argument("--tool", required=True, help="目标工具（mj/banana/sd/seedance_2_0/...）")
    style_validate.add_argument("--file", help="提示词文件路径")
    style_validate.add_argument("--text", help="直接传入提示词文本")
    style_validate.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_validate.set_defaults(func=cmd_style_validate)

    style_apply = style_sub.add_parser("apply", help="把风格卡写入项目（00_project/style-cards/）")
    style_apply.add_argument("ref", help="编号 / 英文名 / 中文名")
    style_apply.add_argument("--project", required=True, help="项目目录或项目名")
    style_apply.add_argument("--tool", help="绑定到某工具（可选）")
    style_apply.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_apply.set_defaults(func=cmd_style_apply)

    style_inject = style_sub.add_parser("inject", help="注入 06/08 提示词并写注入记录")
    style_inject.add_argument("ref", help="编号 / 英文名 / 中文名")
    style_inject.add_argument("--project", required=True, help="项目目录或项目名")
    style_inject.add_argument("--stage", required=True, choices=["06", "08"], help="挂载阶段")
    style_inject.add_argument("--tool", required=True, help="目标工具")
    style_inject.add_argument("--prompt-file", required=True, help="原始提示词文件（UTF-8）")
    style_inject.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_inject.set_defaults(func=cmd_style_inject)

    style_batch = style_sub.add_parser("inject-batch", help="批量注入并写一份批量记录")
    style_batch.add_argument("--project", required=True, help="项目目录或项目名")
    style_batch.add_argument(
        "--batch", required=True,
        help="批量 JSON（{stage, tool, items:[{shot, prompt}]}）",
    )
    style_batch.add_argument("--stage", choices=["06", "08"], help="覆盖 JSON 中的 stage")
    style_batch.add_argument("--tool", help="覆盖 JSON 中的 tool")
    style_batch.add_argument("--out-dir", help="把组合提示词逐条写入该目录")
    style_batch.add_argument(
        "--per-shot-records", action="store_true",
        help="除批量记录外，再为每条写一份独立注入记录（逐镜追溯）",
    )
    style_batch.add_argument("--json", action="store_true", help="以 JSON 输出")
    style_batch.set_defaults(func=cmd_style_inject_batch)

    flow = sub.add_parser("flow", help="可视化节点工作流：列表 / 校验 / 运行 / 本地服务")
    flow_sub = flow.add_subparsers(dest="flow_command", required=True)

    flow_new = flow_sub.add_parser("new", help="新建流程图骨架（start + end）")
    flow_new.add_argument("--project", required=True, help="项目名或项目路径")
    flow_new.add_argument("--name", required=True, help="流程图名称")
    flow_new.add_argument("--graph", help="graph_id（缺省由名称生成）")
    flow_new.add_argument("--template", help="从预置模板创建（见 flow templates）")
    flow_new.add_argument("--force", action="store_true", help="覆盖同名流程图")
    flow_new.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_new.set_defaults(func=cmd_flow_new)

    flow_list = flow_sub.add_parser("list", help="列出项目内流程图")
    flow_list.add_argument("--project", required=True, help="项目名或项目路径")
    flow_list.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_list.set_defaults(func=cmd_flow_list)

    flow_show = flow_sub.add_parser("show", help="输出流程图 JSON")
    flow_show.add_argument("--project", help="项目名或项目路径")
    flow_show.add_argument("--graph", help="graph_id")
    flow_show.add_argument("--file", help="直接指定流程图 JSON 文件")
    flow_show.add_argument("--json", action="store_true", help="以 JSON 输出（默认即 JSON）")
    flow_show.set_defaults(func=cmd_flow_show)

    flow_validate = flow_sub.add_parser("validate", help="校验流程图（契约 + 语义规则）")
    flow_validate.add_argument("--project", help="项目名或项目路径")
    flow_validate.add_argument("--graph", help="graph_id")
    flow_validate.add_argument("--file", help="直接指定流程图 JSON 文件")
    flow_validate.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_validate.set_defaults(func=cmd_flow_validate)

    flow_run = flow_sub.add_parser("run", help="执行流程图（默认按图设置决定 dry-run）")
    flow_run.add_argument("--project", required=True, help="项目名或项目路径")
    flow_run.add_argument("--graph", required=True, help="graph_id")
    flow_run.add_argument(
        "--mode", choices=["full", "to_node", "single"], default="full", help="运行模式"
    )
    flow_run.add_argument("--node", help="目标节点（to_node / single 模式必填）")
    flow_dry = flow_run.add_mutually_exclusive_group()
    flow_dry.add_argument("--dry-run", dest="dry_run", action="store_true", default=None, help="只预演不写盘")
    flow_dry.add_argument("--live", dest="dry_run", action="store_false", default=None, help="真实执行并写盘")
    flow_run.add_argument("--yes", action="store_true", help="自动确认 confirm 节点（无人值守）")
    flow_run.add_argument("--retries", type=int, default=None, help="节点级重试次数覆盖（0-3）")
    flow_run.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_run.set_defaults(func=cmd_flow_run)

    flow_serve = flow_sub.add_parser("serve", help="启动本地可视化工作台（浏览器访问）")
    flow_serve.add_argument("--project", required=True, help="项目名或项目路径")
    flow_serve.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    flow_serve.add_argument("--port", type=int, default=8899, help="监听端口（默认 8899）")
    flow_serve.add_argument("--no-token", action="store_true", help="关闭访问令牌（本机调试用）")
    flow_serve.set_defaults(func=cmd_flow_serve)

    flow_templates = flow_sub.add_parser("templates", help="列出预置流程模板")
    flow_templates.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_templates.set_defaults(func=cmd_flow_templates)

    flow_runs = flow_sub.add_parser("runs", help="列出项目运行历史")
    flow_runs.add_argument("--project", required=True, help="项目名或项目路径")
    flow_runs.add_argument("--limit", type=int, default=20, help="最多显示条数")
    flow_runs.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_runs.set_defaults(func=cmd_flow_runs)

    flow_recover = flow_sub.add_parser("recover", help="从历史运行恢复（可回滚运行前状态快照）")
    flow_recover.add_argument("--project", required=True, help="项目名或项目路径")
    flow_recover.add_argument("--run", required=True, help="run_id")
    flow_recover.add_argument("--restore-state", action="store_true", help="先回滚到运行前状态快照")
    flow_recover.add_argument("--yes", action="store_true", help="自动确认 confirm 节点")
    flow_recover.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_recover.set_defaults(func=cmd_flow_recover)

    flow_batch = flow_sub.add_parser("batch", help="批量运行多个流程图")
    flow_batch.add_argument("--project", required=True, help="项目名或项目路径")
    flow_batch.add_argument("--graphs", help="逗号分隔的 graph_id 列表")
    flow_batch.add_argument("--all", action="store_true", help="运行项目内全部流程图")
    flow_batch_dry = flow_batch.add_mutually_exclusive_group()
    flow_batch_dry.add_argument("--dry-run", dest="dry_run", action="store_true", default=None, help="只预演不写盘")
    flow_batch_dry.add_argument("--live", dest="dry_run", action="store_false", default=None, help="真实执行并写盘")
    flow_batch.add_argument("--yes", action="store_true", help="自动确认 confirm 节点")
    flow_batch.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_batch.set_defaults(func=cmd_flow_batch)

    flow_replay = flow_sub.add_parser("replay", help="查看运行回放（每步耗时与失败定位）")
    flow_replay.add_argument("--project", required=True, help="项目名或项目路径")
    flow_replay.add_argument("--run", required=True, help="run_id")
    flow_replay.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_replay.set_defaults(func=cmd_flow_replay)

    flow_diff = flow_sub.add_parser("diff", help="对比两次运行（状态/耗时/回归）")
    flow_diff.add_argument("--project", required=True, help="项目名或项目路径")
    flow_diff.add_argument("--run", required=True, help="基准 run_id（较早）")
    flow_diff.add_argument("--other-run", required=True, help="对比 run_id（较新）")
    flow_diff.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_diff.set_defaults(func=cmd_flow_diff)

    flow_export = flow_sub.add_parser("export", help="导出流程图 JSON（stdout 或 --out）")
    flow_export.add_argument("--file", help="直接导出指定流程图 JSON 文件")
    flow_export.add_argument("--project", help="项目名或项目路径")
    flow_export.add_argument("--graph", help="graph_id")
    flow_export.add_argument("--out", help="输出文件路径（缺省打印到标准输出）")
    flow_export.set_defaults(func=cmd_flow_export)

    flow_import = flow_sub.add_parser("import", help="从 JSON 文件导入流程图")
    flow_import.add_argument("--project", required=True, help="项目名或项目路径")
    flow_import.add_argument("--file", required=True, help="流程图 JSON 文件")
    flow_import.add_argument("--graph", help="导入后的 graph_id（缺省用文件内 graph_id）")
    flow_import.add_argument("--force", action="store_true", help="覆盖同名流程图")
    flow_import.add_argument("--json", action="store_true", help="以 JSON 输出")
    flow_import.set_defaults(func=cmd_flow_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:  # 控制台编码不安全时避免中文/JSON 输出直接崩溃
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        _print("已中断")
        return EXIT_FAIL
    except BrokenPipeError:
        return EXIT_FAIL
