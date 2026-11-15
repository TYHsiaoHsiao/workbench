"""项目初始化与状态存取：真实文档目录探测、项目模板、状态卡 v2。

状态文件 `00_project/state.json` 是项目唯一事实来源；
参考记忆的机器可读文件为 `00_project/reference-memory.json`，同目录 `.md` 为只读人读视图。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from core_router.gates import ensure_stage_gates, gate_detail
from core_router.registry import Registry, load_registry
from core_router.state import default_state, validate_state

PROJECT_DIRS = [
    "00_project",
    "00_project/history",
    "00_project/knowledge-cards",
    "00_project/style-cards",
    "00_inbox",
    "01_story",
    "02_script",
    "03_assets",
    "04_performance",
    "05_shots",
    "05_shots/keyframes",
    "06_prompts",
]

REFERENCE_MEMORY_JSON = "reference-memory.json"
REFERENCE_MEMORY_MD = "reference-memory.md"

AGENTS_TEMPLATE = """# 项目总控（工作台生成）

本项目由 AI 影视工作台创建，按阶段推进：
01 概念锚定 -> 02 角色圣经 -> 03 世界观（可选）-> 04 分场大纲 -> 05 剧本深度融合
-> 06 图像资产 -> 07 表演 -> 08 视频提示词。

- 入口：A 从零 / B 完整剧本 / C 部分资料 / D 高手优化；记录在 `00_project/state.json`，确认一次不重复询问。
- 状态、门禁与版本以 `00_project/state.json` 为唯一事实来源；阶段推进请运行 `workbench.py next`，门禁未通过会被拒绝。
- 每阶段只执行一个 Skill；先读 `00_project/state.json` 与 `00_project/reference-memory.json`，写状态后再进入下一阶段。
- 阶段结果同时展示在聊天并保存为 Markdown；修订先写新版本（v01 -> v02），上游变更标记受影响下游。
- 本地知识库默认关闭；只有用户明确说「调用本地知识库 / 知识库B / 知识库C / 匹配本地参考」才检索。
  确认后的方法写入 `00_project/reference-memory.json`（`.md` 只是人读视图）。
- 08 内部先出 `05_shots/` 镜头规划并等待确认，再写 `06_prompts/` 提示词，不是第 09 阶段。
- 每条视频提示词必须独立写全站位、姿势、道具、场景、光线、轴线、动作起点与台词，
  禁止「上一镜头 / 继续 / 同上 / 保持原样」。

当前入口与阶段以 `00_project/state.json` 为准。
"""

BRIEF_TEMPLATE = """# 一句话需求

（待填写）

## 基础信息
- 受众：
- 目标平台：
- 目标时长：
- 内容类型：
- 视觉方向：
- 目标视频模型：
- 连续性模式：
- 预算：
- 不能出现的内容：
"""

REFERENCE_MEMORY_MD_NOTICE = (
    "> 本文件是人读视图；机器可读的唯一事实来源为同目录 `reference-memory.json`。"
    "如需修改，请改 JSON 后重新生成。\n"
)

REFERENCE_MEMORY_MD_BODY = """# 跨阶段参考记忆

状态：启用
知识库外挂状态：未调用
下一参考编号：参考方法001

## 权威顺序
1. 用户本轮明确要求
2. 最新已确认的项目阶段文件
3. 启用的参考方法
4. 模型通用知识

## 已确认参考
暂无。

## 参考变更记录
暂无。

## 阶段应用记录
暂无。
"""


class ProjectError(RuntimeError):
    """项目初始化或状态存取失败时抛出。"""


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def workbench_home() -> Path:
    override = os.environ.get("AI_FILM_WORKBENCH_HOME")
    return Path(override) if override else Path.home() / ".ai-film-workbench"


def load_config() -> dict[str, Any]:
    path = workbench_home() / "config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_documents_dir() -> Path:
    """探测用户真实文档目录（Windows 走 Shell 已知文件夹，其他平台走常见路径）。"""
    override = os.environ.get("AI_FILM_DOCUMENTS_DIR")
    if override and Path(override).is_dir():
        return Path(override)
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(1024)
            # CSIDL_PERSONAL = 5；返回 0 表示成功。
            result = ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer)
            if result == 0 and buffer.value:
                candidate = Path(buffer.value)
                if candidate.is_dir():
                    return candidate
        except (AttributeError, OSError, ValueError):
            pass
    for candidate in (Path.home() / "Documents", Path.home() / "文档"):
        if candidate.is_dir():
            return candidate
    return Path.home()


def default_projects_root() -> Path:
    env_root = os.environ.get("AI_FILM_PROJECTS_ROOT")
    if env_root:
        return Path(env_root)
    config = load_config()
    configured = (config.get("projects") or {}).get("root")
    if configured:
        return Path(configured)
    return detect_documents_dir() / "AI 影视工作台" / "projects"


def build_state(project: str, entry: str = "A", mode: str = "full",
                stage: str = "01", registry: Registry | None = None) -> dict[str, Any]:
    """构造状态卡 v2：在 v1 基础上补齐门禁、知识桥、风格、修订日志等字段。"""
    registry = registry or load_registry()
    state = default_state(project=project, entry=entry, mode=mode, stage=stage)
    state.update(
        {
            "documents_root": str(detect_documents_dir()),
            "projects_root": str(default_projects_root()),
            "confirmed_files": [],
            "knowledge_bridge": {"status": "off", "last_card": "", "confirmed_references": []},
            "style": {"status": "off", "profile_path": ""},
            "stage_artifacts": {},
            "revision_log": [
                {"at": now(), "action": "created", "stage": stage,
                 "note": "工作台创建项目"}
            ],
        }
    )
    ensure_stage_gates(state, stage, registry)
    errors = validate_state(state)
    if errors:
        raise ProjectError("初始状态不合法: " + "; ".join(errors))
    return state


def _status_card(state: dict[str, Any], stage_name: str,
                 registry: Registry | None = None) -> str:
    registry = registry or load_registry()
    gate_lines = ["| 门禁 | 类型 | 状态 | 说明 |", "|---|---|---|---|"]
    for item in gate_detail(state, state["stage"], registry):
        gate_lines.append(
            f"| {item['id']} | {item['type']} | {item['status']} | {item['description']} |"
        )
    bridge = state.get("knowledge_bridge", {})
    return f"""# 项目状态卡

| 字段 | 值 |
|---|---|
| 项目名称 | {state['project']} |
| 入口 | {state['entry']} |
| 运行模式 | {state['mode']} |
| 当前阶段 | {state['stage']} {stage_name} |
| 状态版本 | {state['version']} |
| 知识桥状态 | {bridge.get('status', 'off')} |
| 跨阶段参考记忆 | `00_project/reference-memory.json`（`.md` 为只读视图） |
| 文档目录 | {state.get('documents_root', '')} |
| 项目根目录 | {state.get('projects_root', '')} |
| 作者剧本锁定 | 见 state.json |
| 备注 | 状态唯一事实来源为 `00_project/state.json`；本卡由工作台生成，只读 |

## 本阶段门禁

{chr(10).join(gate_lines)}

## 目录约定
- `00_project/`：状态、参考记忆、历史版本、知识卡与风格卡
- `01_story/`：概念锚定、角色、世界观、分场大纲
- `02_script/`：剧本
- `03_assets/`：图像资产
- `04_performance/`：表演
- `05_shots/`：镜头规划与连续性清单（含 `keyframes/`）
- `06_prompts/`：视频提示词
- `00_inbox/`：用户投入的原始资料
"""


def reference_memory_md() -> str:
    return REFERENCE_MEMORY_MD_NOTICE + "\n" + REFERENCE_MEMORY_MD_BODY


def create_project(name: str, base: str | Path | None = None, entry: str = "A",
                   mode: str = "full", force: bool = False,
                   registry: Registry | None = None) -> dict[str, Any]:
    """创建项目骨架；目标已存在且未 force 时抛 ProjectError。"""
    project = (name or "").strip()
    if not project:
        raise ProjectError("项目名称不能为空")
    registry = registry or load_registry()
    root = Path(base) if base is not None else default_projects_root()
    target = root / project
    existed = target.exists()
    if existed and not force:
        raise ProjectError(f"目标已存在，未覆盖: {target}（如需覆盖请加 --force）")

    for rel in PROJECT_DIRS:
        (target / rel).mkdir(parents=True, exist_ok=True)

    state = build_state(project, entry=entry, mode=mode, stage="01", registry=registry)
    save_state(target, state)
    (target / "00_project" / "brief.md").write_text(BRIEF_TEMPLATE, encoding="utf-8")
    (target / "00_project" / REFERENCE_MEMORY_JSON).write_text(
        json.dumps({"contract_version": "1.0", "entries": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (target / "00_project" / REFERENCE_MEMORY_MD).write_text(
        reference_memory_md(), encoding="utf-8"
    )
    (target / "AGENTS.md").write_text(AGENTS_TEMPLATE, encoding="utf-8")
    (target / "状态卡.md").write_text(
        _status_card(state, registry.stage("01")["name"], registry), encoding="utf-8"
    )

    return {
        "ok": True,
        "project": project,
        "path": str(target),
        "project_root": str(root),
        "entry": entry,
        "mode": mode,
        "stage": "01",
        "stage_name": registry.stage("01")["name"],
        "overwritten": existed,
        "created": PROJECT_DIRS,
        "state_file": str(target / "00_project" / "state.json"),
        "reference_memory": str(target / "00_project" / REFERENCE_MEMORY_JSON),
    }


def state_path(project_root: str | Path) -> Path:
    return Path(project_root) / "00_project" / "state.json"


def load_state(project_root: str | Path) -> dict[str, Any]:
    path = state_path(project_root)
    if not path.is_file():
        raise ProjectError(f"{path}: 缺少项目状态文件")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"{path}: JSON 解析失败: {exc}") from exc
    errors = validate_state(state)
    if errors:
        raise ProjectError(f"{path}: 状态契约校验失败: " + "; ".join(errors))
    return state


def save_state(project_root: str | Path, state: dict[str, Any]) -> Path:
    errors = validate_state(state)
    if errors:
        raise ProjectError("状态契约校验失败: " + "; ".join(errors))
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def refresh_status_card(project_root: str | Path, registry: Registry | None = None) -> None:
    registry = registry or load_registry()
    state = load_state(project_root)
    stage_name = "已完成" if state["stage"] == "done" else registry.stage(state["stage"])["name"]
    (Path(project_root) / "状态卡.md").write_text(
        _status_card(state, stage_name, registry), encoding="utf-8"
    )


def register_artifacts(
    project_root: str | Path,
    stage: str,
    kind: str,
    paths: list[str],
    note: str = "",
    next_action: str | None = None,
) -> dict[str, Any]:
    """把阶段产物登记进 state.stage_artifacts（含 sha256 摘要），写 revision_log。

    paths 支持相对项目根目录的路径、glob 模式，以及项目内的绝对路径。
    """
    root = Path(project_root)
    stage = str(stage)
    kind = (kind or "").strip()
    if stage not in {f"0{index}" for index in range(1, 9)} | {"done"}:
        raise ProjectError(f"未知阶段: {stage}")
    if not kind:
        raise ProjectError("产物类型不能为空")
    if not paths:
        raise ProjectError("至少需要一个产物路径")
    state = load_state(root)

    files: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for pattern in paths:
        candidate = Path(pattern)
        if candidate.is_absolute():
            matches = [candidate] if candidate.is_file() else []
            missing.extend([] if matches else [pattern])
            base = candidate
        else:
            base = root / pattern
            if any(char in pattern for char in "*?["):
                matches = [item for item in sorted(root.glob(pattern)) if item.is_file()]
            else:
                matches = [base] if base.is_file() else []
            if not matches:
                missing.append(pattern)
        for item in matches:
            try:
                item.resolve().relative_to(root.resolve())
            except ValueError:
                raise ProjectError(f"产物不在项目目录内: {item}")
            relative = item.relative_to(root).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            digest = hashlib.sha256(item.read_bytes()).hexdigest()
            files.append(
                {
                    "path": relative,
                    "sha256": digest,
                    "bytes": item.stat().st_size,
                }
            )
    if not files:
        raise ProjectError("没有找到可登记的文件: " + "；".join(missing or paths))

    total = sum(item["bytes"] for item in files)
    summary = (
        f"{kind}：{len(files)} 个文件，{total} 字节；"
        + "；".join(f"{item['path']} sha256={item['sha256'][:16]}" for item in files)
    )
    state.setdefault("stage_artifacts", {})[stage] = summary
    log_note = note or f"{kind}：{len(files)} 个文件"
    state.setdefault("revision_log", []).append(
        {"at": now(), "action": "artifact_registered", "stage": stage, "note": log_note}
    )
    if next_action:
        state["next_action"] = str(next_action)
    state_file = save_state(root, state)
    refresh_status_card(root)
    return {
        "ok": True,
        "stage": stage,
        "kind": kind,
        "files": files,
        "missing": missing,
        "summary": summary,
        "state_file": str(state_file),
    }


def update_knowledge_bridge(
    project_root: str | Path,
    status: str,
    last_card: str | None = None,
    confirmed_references: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """更新 state.knowledge_bridge（off/requested/on），供 CLI 使用。"""
    if status not in {"off", "requested", "on"}:
        raise ProjectError(f"知识桥状态必须是 off/requested/on：{status}")
    root = Path(project_root)
    state = load_state(root)
    bridge = dict(state.get("knowledge_bridge") or {"status": "off"})
    bridge["status"] = status
    if last_card is not None:
        bridge["last_card"] = str(last_card)
    if confirmed_references is not None:
        bridge["confirmed_references"] = [str(item) for item in confirmed_references]
    if note:
        bridge["note"] = str(note)
    state["knowledge_bridge"] = bridge
    state_file = save_state(root, state)
    refresh_status_card(root)
    return {"ok": True, "knowledge_bridge": bridge, "state_file": str(state_file)}


EXPORT_METADATA = "export-metadata.json"


def _archive_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def export_project(project_root: str | Path, out_path: str | Path | None = None,
                   *, overwrite: bool = False) -> dict[str, Any]:
    """把整个项目目录打包成可迁移 ZIP（含 export-metadata.json）。"""
    root = Path(project_root)
    if not root.is_dir():
        raise ProjectError(f"项目目录不存在: {root}")
    state = load_state(root)
    if out_path is None:
        out = root / "00_project" / "history" / f"project-{state['version']}-{_archive_stamp()}.zip"
    else:
        out = Path(out_path)
    if out.exists() and not overwrite:
        raise ProjectError(f"导出目标已存在，未覆盖: {out}（如需覆盖请加 --force）")
    files = sorted(
        item for item in root.rglob("*")
        if item.is_file() and not item.name.endswith(".tmp")
    )
    relative = [item.relative_to(root).as_posix() for item in files]
    metadata = {
        "contract_version": "1.0",
        "project": state["project"],
        "state_version": state["version"],
        "stage": state["stage"],
        "entry": state["entry"],
        "exported_at": now(),
        "files": len(files),
        "relative_paths": relative,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item, name in zip(files, relative):
            archive.write(item, name)
        archive.writestr(
            EXPORT_METADATA, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
        )
    return {
        "ok": True,
        "archive": str(out),
        "project": state["project"],
        "state_version": state["version"],
        "stage": state["stage"],
        "files": len(files),
        "bytes": out.stat().st_size,
    }


def restore_project(archive_path: str | Path, dest_root: str | Path) -> dict[str, Any]:
    """从导出的 ZIP 还原项目到 dest_root/<项目名>；拒绝路径穿越与非空覆盖。"""
    archive_file = Path(archive_path)
    if not archive_file.is_file():
        raise ProjectError(f"导出包不存在: {archive_file}")
    dest = Path(dest_root)
    with zipfile.ZipFile(archive_file) as archive:
        names = archive.namelist()
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise ProjectError(f"导出包含非法路径: {name}")
        metadata: dict[str, Any] = {}
        if EXPORT_METADATA in names:
            metadata = json.loads(archive.read(EXPORT_METADATA).decode("utf-8"))
        project = str(metadata.get("project") or archive_file.stem)
        target = dest / project
        if target.exists() and any(target.iterdir()):
            raise ProjectError(f"目标项目目录非空，未覆盖: {target}")
        for name in names:
            if name == EXPORT_METADATA:
                continue
            archive.extract(name, target)
    state = load_state(target)
    refresh_status_card(target)
    return {
        "ok": True,
        "project": state["project"],
        "path": str(target),
        "state_version": state["version"],
        "stage": state["stage"],
        "files": len([name for name in names if name != EXPORT_METADATA]),
    }
