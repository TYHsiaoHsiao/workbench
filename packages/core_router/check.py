"""跨阶段内容一致性检查（从 CLI 抽出，供流程节点复用）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ARTIFACT_TOKEN = re.compile(r"[0-9A-Za-z_\u4e00-\u9fff./\-]+\.(?:md|json|txt)")
SCENE_ROW = re.compile(r"^\|\s*(1-0[1-8])\b")
SCENE_BUDGET = re.compile(r"场次时长预算[：:]\s*(\d+)\s*s")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scene_seconds(text: str) -> dict[str, int]:
    """从以 `| 1-0X |` 开头的表格行里取第一段「N s / N 秒」。"""
    result: dict[str, int] = {}
    for line in text.splitlines():
        match = SCENE_ROW.match(line)
        if not match:
            continue
        found = re.findall(r"(\d+)\s*(?:s|秒)(?![A-Za-z0-9])", line)
        if found:
            result[match.group(1)] = int(found[0])
    return result


def content_checks(project_dir: Path, state: dict[str, Any]) -> tuple[list[str], list[str]]:
    """阶段内容一致性检查：风格/知识桥引用、产物存在性、跨阶段时长。"""
    errors: list[str] = []
    warnings: list[str] = []

    style = state.get("style") or {}
    if style.get("status") == "on":
        profile_path = style.get("profile_path")
        if not profile_path:
            errors.append("style.status=on 但缺少 profile_path")
        elif not (project_dir / str(profile_path)).is_file():
            errors.append(f"风格卡文件不存在: {profile_path}")
    elif style.get("status") == "off" and style.get("profile_path"):
        warnings.append("style.status=off 但仍保留 profile_path")

    bridge = state.get("knowledge_bridge") or {}
    bridge_status = bridge.get("status", "off")
    last_card = bridge.get("last_card")
    if bridge_status in {"requested", "on"}:
        if not last_card:
            errors.append(f"knowledge_bridge.status={bridge_status} 但缺少 last_card")
        elif not (project_dir / str(last_card)).is_file():
            errors.append(f"知识卡文件不存在: {last_card}")
    if bridge_status == "on":
        confirmed = bridge.get("confirmed_references") or []
        if not confirmed:
            errors.append("knowledge_bridge.status=on 但 confirmed_references 为空")
        known = set(state.get("references") or [])
        for ref in confirmed:
            if ref not in known:
                errors.append(f"confirmed_references 中的 {ref} 不在 state.references")

    artifacts = state.get("stage_artifacts") or {}
    checked: set[str] = set()
    for key, value in artifacts.items():
        tokens: list[str] = []
        if "/" in str(key) or str(key).endswith((".md", ".json", ".txt")):
            tokens.append(str(key))
        if isinstance(value, str):
            tokens.extend(ARTIFACT_TOKEN.findall(value))
        for token in tokens:
            rel = token.strip("/")
            if rel in checked or " " in rel:
                continue
            checked.add(rel)
            if "/" not in rel:
                # 裸文件名无法确定所在目录（多为旧版自由文本摘要），跳过核验
                continue
            if not (project_dir / rel).exists():
                errors.append(f"stage_artifacts 引用的文件不存在: {rel}")

    if state.get("stale_downstream"):
        warnings.append(f"stale_downstream 非空: {state['stale_downstream']}")

    treatment = project_dir / "01_story" / "treatment.md"
    acting = project_dir / "04_performance" / "acting-v01.md"
    shot_dir = project_dir / "05_shots"
    if treatment.is_file() and shot_dir.is_dir():
        budgets = scene_seconds(read_text(treatment))
        for plan in sorted(shot_dir.glob("1-0[1-8]-shot-plan-v*.md")):
            match = re.match(r"(1-0[1-8])", plan.name)
            if not match:
                continue
            scene = match.group(1)
            found = SCENE_BUDGET.search(read_text(plan))
            if scene in budgets and found and budgets[scene] != int(found.group(1)):
                errors.append(
                    f"时长不一致: 场次 {scene} treatment={budgets[scene]}s，shot-plan={found.group(1)}s"
                )
        if acting.is_file():
            acting_seconds = scene_seconds(read_text(acting))
            for scene, seconds in acting_seconds.items():
                if scene in budgets and budgets[scene] != seconds:
                    warnings.append(
                        f"时长提示不一致: 场次 {scene} treatment={budgets[scene]}s，acting 交接={seconds}s"
                    )
    return errors, warnings


__all__ = ["ARTIFACT_TOKEN", "SCENE_BUDGET", "SCENE_ROW", "content_checks", "read_text", "scene_seconds"]
