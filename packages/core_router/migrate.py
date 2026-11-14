"""旧项目迁移与规则升级：备份、状态卡 v2 合并、参考记忆 MD -> JSON、目录补齐。

原则：
- 先备份到 `00_project/history/<动作>-<时间戳>/`，可回滚；
- 不改创作文件（01_story / 02_script / ...）；
- 已有参考记忆不丢失：能解析的条目迁移为 JSON，原 MD 保留为 `.legacy.md`；
- 迁移/升级过程写报告，便于人工复核。
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any

from core_router.gates import ensure_stage_gates
from core_router.project import (
    AGENTS_TEMPLATE,
    PROJECT_DIRS,
    REFERENCE_MEMORY_JSON,
    REFERENCE_MEMORY_MD,
    ProjectError,
    build_state,
    load_state,
    refresh_status_card,
    save_state,
)
from core_router.registry import Registry, load_registry
from core_router.state import default_state, validate_state

LEGACY_STATE_FILES = [
    "state.json",
    "brief.md",
    "project-status.md",
    "routing.md",
    REFERENCE_MEMORY_MD,
    "00-本地知识库参考记忆.md",
]
LEGACY_REFERENCE_NAMES = [REFERENCE_MEMORY_MD, "00-本地知识库参考记忆.md"]
LEGACY_UPGRADE_FILES = ["AGENTS.md", "状态卡.md"]
REFERENCE_ID_RE = re.compile(r"^#+\s*(参考方法[0-9]{3})")


class MigrationError(RuntimeError):
    """迁移/升级无法安全执行时抛出。"""


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _parse_md_fields(text: str) -> dict[str, str]:
    """解析旧状态卡/路由表的「字段: 值」或表格行。"""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] and cells[0] not in ("字段", "---"):
                fields[cells[0]] = cells[1]
            continue
        for sep in ("：", ":"):
            if sep in stripped:
                key, _, value = stripped.partition(sep)
                key, value = key.strip(), value.strip()
                if key and value:
                    fields.setdefault(key, value)
                break
    return fields


def _norm_stage(value: str | None) -> str:
    if not value:
        return "01"
    match = re.search(r"0[1-8]", value)
    return match.group(0) if match else "01"


def _norm_entry(value: str | None) -> str:
    if value:
        match = re.search(r"[ABCD]", value.upper())
        if match:
            return match.group(0)
    return "A"


def _parse_reference_entries(text: str) -> list[dict[str, Any]]:
    """把旧 Markdown「参考方法NNN」小节尽量迁移为契约条目（不确定值标注待核对）。"""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    fields: dict[str, str] = {}

    def flush() -> None:
        nonlocal current, fields
        if not current:
            return
        at = datetime.datetime.now().isoformat(timespec="seconds")
        scope_map = {"故事创作": ["story_01_05"], "图像": ["image_06"],
                     "表演": ["performance_07"], "视频镜头": ["camera_08"]}
        scope_text = fields.get("使用范围") or fields.get("适用范围") or "故事创作（01-05）"
        scope = ["story_01_05"]
        for key, value in scope_map.items():
            if key in scope_text:
                scope = value
                break
        entries.append(
            {
                "id": current["id"],
                "status": "enabled" if "停用" not in (fields.get("状态") or "") else "disabled",
                "source": fields.get("来源名称") or fields.get("来源") or "迁移待核对",
                "type": "other",
                "local_path": fields.get("本地路径") or "（迁移待核对）",
                "page_hits": fields.get("页码与命中词") or "（迁移待核对）",
                "method": fields.get("可迁移方法") or "（迁移待核对）",
                "scope": scope,
                "stage": "01",
                "binding_facts": [],
                "forbidden": [],
                "confirmed": {"by": "migration", "at": at},
                "change_log": [
                    {"at": at, "action": "created", "note": "由旧 Markdown 参考记忆迁移，需人工核对"}
                ],
            }
        )
        current = None
        fields = {}

    for line in text.splitlines():
        stripped = line.strip()
        match = REFERENCE_ID_RE.match(stripped)
        if match:
            flush()
            current = {"id": match.group(1)}
            continue
        if not current:
            continue
        for sep in ("：", ":"):
            if sep in stripped:
                key, _, value = stripped.partition(sep)
                key, value = key.strip().lstrip("-* "), value.strip()
                if key and value:
                    fields.setdefault(key, value)
                break
    flush()
    return entries


def _state_from_legacy(root: Path, legacy: dict[str, Any]) -> dict[str, Any]:
    base = default_state(root.name, entry="A", mode="full", stage="01")
    status_fields: dict[str, str] = {}
    routing_fields: dict[str, str] = {}
    for name in ("project-status.md", "routing.md"):
        path = root / "00_project" / name
        if path.is_file():
            parsed = _parse_md_fields(path.read_text(encoding="utf-8", errors="replace"))
            if name == "project-status.md":
                status_fields = parsed
            else:
                routing_fields = parsed

    merged = dict(base)
    merged["project"] = (
        legacy.get("project")
        or status_fields.get("项目名称")
        or root.name
    )
    merged["entry"] = _norm_entry(
        legacy.get("entry") or status_fields.get("入口") or routing_fields.get("项目入口")
    )
    merged["mode"] = legacy.get("mode") if legacy.get("mode") in (
        "full", "stage", "relay", "revise"
    ) else "full"
    merged["stage"] = _norm_stage(
        legacy.get("stage") or status_fields.get("当前阶段") or routing_fields.get("当前阶段")
    )
    merged["version"] = legacy.get("version") if isinstance(legacy.get("version"), str) else "v01"
    raw_inputs = legacy.get("authoritative_inputs")
    if isinstance(raw_inputs, list):
        merged["authoritative_inputs"] = [str(item) for item in raw_inputs if str(item).strip()]
    else:
        field_text = (status_fields.get("本轮权威输入") or "").strip()
        merged["authoritative_inputs"] = [
            part.strip() for part in re.split(r"[、,;；]", field_text) if part.strip()
        ]
    merged["references"] = [
        item for item in (legacy.get("references") or []) if isinstance(item, str)
    ]
    merged["stale_downstream"] = list(legacy.get("stale_downstream") or [])
    merged["next_action"] = legacy.get("next_action") or "迁移完成：核对状态卡与参考记忆后继续"
    merged.setdefault("revision_log", [])
    merged["revision_log"].append(
        {"at": datetime.datetime.now().isoformat(timespec="seconds"),
         "action": "migrated", "stage": merged["stage"], "note": "旧项目迁移到状态卡 v2"}
    )
    return merged


def migrate_project(project_root: str | Path,
                    registry: Registry | None = None) -> dict[str, Any]:
    """把旧项目迁移为状态卡 v2 + 参考记忆 JSON；返回迁移报告。"""
    registry = registry or load_registry()
    root = Path(project_root)
    proj = root / "00_project"
    if not proj.is_dir():
        raise MigrationError(f"{root}: 不是工作台项目（缺少 00_project/）")

    stamp = _stamp()
    backup = proj / "history" / f"migrate-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    for name in LEGACY_STATE_FILES:
        source = proj / name
        if source.is_file():
            shutil.copy2(source, backup / name)
            copied.append(name)

    legacy_state = _read_json(proj / "state.json") or {}
    state = _state_from_legacy(root, legacy_state)
    state.update(
        {
            "knowledge_bridge": legacy_state.get("knowledge_bridge")
            or {"status": "off", "last_card": "", "confirmed_references": []},
            "style": legacy_state.get("style") or {"status": "off", "profile_path": ""},
            "confirmed_files": list(legacy_state.get("confirmed_files") or []),
            "stage_artifacts": dict(legacy_state.get("stage_artifacts") or {}),
        }
    )
    ensure_stage_gates(state, state["stage"], registry)
    errors = validate_state(state)
    if errors:
        raise MigrationError("迁移后状态不合法: " + "; ".join(errors))
    save_state(root, state)

    memory_entries = _read_json(proj / REFERENCE_MEMORY_JSON)
    migrated_entries: list[dict[str, Any]] = []
    legacy_md_name: str | None = None
    if memory_entries and isinstance(memory_entries.get("entries"), list):
        migrated_entries = memory_entries["entries"]
    else:
        for name in LEGACY_REFERENCE_NAMES:
            md_path = proj / name
            if md_path.is_file():
                migrated_entries = _parse_reference_entries(
                    md_path.read_text(encoding="utf-8", errors="replace")
                )
                legacy_md_name = name
                break
    memory = {"contract_version": "1.0", "entries": migrated_entries}
    (proj / REFERENCE_MEMORY_JSON).write_text(
        json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if legacy_md_name:
        original = proj / legacy_md_name
        target = proj / "reference-memory.legacy.md"
        if original != target:
            original.replace(target)

    refresh_status_card(root, registry)

    report = {
        "ok": True,
        "project": str(root),
        "project_name": state["project"],
        "stage": state["stage"],
        "entry": state["entry"],
        "backup": str(backup),
        "backed_up": copied,
        "reference_entries": len(migrated_entries),
        "legacy_memory_retired": legacy_md_name,
        "state_file": str(proj / "state.json"),
        "reference_memory": str(proj / REFERENCE_MEMORY_JSON),
        "notes": [
            "创作文件未改动",
            "参考记忆条目如标注「迁移待核对」，请人工补齐路径/页码/命中词",
        ],
    }
    (proj / "migration-report.md").write_text(_render_report(report), encoding="utf-8")
    return report


def _render_report(report: dict[str, Any]) -> str:
    lines = [
        "# 项目迁移报告",
        "",
        f"- 时间：{datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- 项目：{report['project_name']}（{report['project']}）",
        f"- 当前阶段：{report['stage']}；入口：{report['entry']}",
        f"- 备份目录：`{report['backup']}`",
        f"- 备份文件：{', '.join(report['backed_up']) or '无'}",
        f"- 迁移参考条目：{report['reference_entries']}",
        f"- 旧版参考记忆：{report['legacy_memory_retired'] or '无'}",
        "",
        "## 说明",
        "",
        "- 状态唯一事实来源已切换为 `00_project/state.json`（状态卡 v2）。",
        "- 参考记忆唯一事实来源已切换为 `00_project/reference-memory.json`；旧 MD 已改名保留。",
        "- 创作目录（01_story / 02_script / 03_assets / 04_performance / 05_shots / 06_prompts）未改动。",
    ]
    return "\n".join(lines) + "\n"


def upgrade_project_rules(project_root: str | Path,
                          registry: Registry | None = None) -> dict[str, Any]:
    """旧项目规则升级：备份后用工作台模板更新 AGENTS/状态卡，补齐目录，不动创作文件。"""
    registry = registry or load_registry()
    root = Path(project_root)
    proj = root / "00_project"
    if not proj.is_dir():
        raise MigrationError(f"{root}: 不是工作台项目（缺少 00_project/）")
    if not (proj / "state.json").is_file():
        raise MigrationError("缺少 00_project/state.json：请先运行 migrate 迁移")

    stamp = _stamp()
    backup = proj / "history" / f"upgrade-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    for rel in ["AGENTS.md", "状态卡.md", "00_project/routing.md", "00_project/project-status.md"]:
        source = root / rel
        if source.is_file():
            target = backup / rel.replace("/", "__")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(rel)

    for rel in PROJECT_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)

    state = load_state(root)
    ensure_stage_gates(state, state["stage"], registry)
    save_state(root, state)

    (root / "AGENTS.md").write_text(AGENTS_TEMPLATE, encoding="utf-8")
    refresh_status_card(root, registry)
    report = {
        "ok": True,
        "project": str(root),
        "stage": state["stage"],
        "backup": str(backup),
        "backed_up": copied,
        "rules_file": str(root / "AGENTS.md"),
        "state_file": str(proj / "state.json"),
        "notes": ["创作文件未改动；参考记忆保留", "规则文件已按工作台模板更新（旧版本在备份目录）"],
    }
    (proj / "upgrade-report.md").write_text(
        "# 项目规则升级报告\n\n"
        f"- 时间：{datetime.datetime.now().isoformat(timespec='seconds')}\n"
        f"- 项目：{root}\n"
        f"- 当前阶段：{state['stage']}\n"
        f"- 备份目录：`{backup}`\n"
        f"- 备份文件：{', '.join(copied) or '无'}\n\n"
        "## 说明\n\n"
        "- `AGENTS.md` 与 `状态卡.md` 已按工作台模板更新；旧版本在备份目录。\n"
        "- `00_story` 等创作目录未改动；参考记忆 JSON 未改动。\n",
        encoding="utf-8",
    )
    return report
