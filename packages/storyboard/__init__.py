# -*- coding: utf-8 -*-
"""storyboard —— 故事成片（工作台内建）：故事 → 分镜 / 提示词 / 字幕 / 配音单 / 多风格对比。

核心算法在 core.py（原 story2prompt 独立工具迁入），本模块提供无 CLI 副作用的封装。
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from . import core

STYLES = core.STYLES
ASPECTS = core.ASPECTS
DEMO_STORY = core.DEMO_STORY
DEFAULT_DURATION = 60
DEFAULT_ASPECT = "9:16"
DEFAULT_STYLE = "悬疑"

PLATFORM_FILES = ("即梦提示词.txt", "可灵提示词.txt", "Seedance提示词.txt")
PREVIEW_FILE = "分镜与提示词.html"
COMPARE_HTML = "多风格对比.html"


class StoryboardError(ValueError):
    """参数/输入错误（可直接展示给用户）。"""


def new_run_id() -> str:
    return f"sb-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def _normalize_compare(value: Any) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).replace("，", ",").split(",")
    names: list[str] = []
    for item in items:
        name = str(item).strip()
        if name in STYLES and name not in names:
            names.append(name)
    return names


def generate(
    story: str,
    *,
    title: str = "",
    duration: int = DEFAULT_DURATION,
    aspect: str = DEFAULT_ASPECT,
    style: str = DEFAULT_STYLE,
    shots: int | None = None,
    prefix: str = "",
    compare: Any = None,
) -> dict[str, Any]:
    """只计算不落盘：返回标题/角色/风格/分镜列表/对比风格。"""
    story = (story or "").strip()
    if not story:
        raise StoryboardError("故事内容为空，请至少写一句话。")
    if aspect not in ASPECTS:
        raise StoryboardError(f"画幅只支持 {', '.join(ASPECTS)}")
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        raise StoryboardError("时长需要整数秒") from None
    if duration < 5 or duration > 600:
        raise StoryboardError("时长需在 5–600 秒之间")
    try:
        shots = int(shots) if shots else None
    except (TypeError, ValueError):
        raise StoryboardError("镜数需要整数") from None
    if shots is not None and (shots < 1 or shots > 60):
        raise StoryboardError("镜数需在 1–60 之间")
    style_name = style if style in STYLES else DEFAULT_STYLE
    merged_style = dict(STYLES[style_name])
    if prefix:
        merged_style["prefix"] = prefix
    try:
        shot_list, auto_title, character = core.build_shots(story, duration, shots)
    except ValueError as exc:
        raise StoryboardError(str(exc)) from None
    final_title = (title or auto_title).strip() or "未命名短片"
    return {
        "story": story,
        "title": final_title[:40],
        "character": character,
        "style_name": style_name,
        "style": merged_style,
        "aspect": aspect,
        "duration": duration,
        "shots": shot_list,
        "compare": _normalize_compare(compare),
    }


def write_package(out_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    """按既定命名落盘全套文件，返回文件清单与镜号预览。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = data["shots"]
    title = data["title"]
    style_name = data["style_name"]
    style = data["style"]
    aspect = data["aspect"]
    duration = data["duration"]
    character = data["character"]

    (out_dir / "分镜表.md").write_text(
        f"# 《{title}》分镜表\n\n" + core.fmt_table(shots) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "提示词包.md").write_text(
        core.build_prompt_md(
            shots, title=title, style_name=style_name, style=style,
            aspect=aspect, character=character, duration=duration,
        ),
        encoding="utf-8", newline="\n"
    )
    prompts = "\n".join(
        core.shot_prompt(shot, style=style, aspect=aspect, character=character)
        for shot in shots
    )
    (out_dir / "prompts.txt").write_text(prompts + "\n", encoding="utf-8")
    (out_dir / PREVIEW_FILE).write_text(
        core.build_html(
            shots, title=title, style_name=style_name, style=style,
            aspect=aspect, character=character, duration=duration,
        ),
        encoding="utf-8", newline="\n"
    )
    core.build_platform_files(out_dir, shots, style=style, aspect=aspect, character=character)
    (out_dir / "字幕.srt").write_text(core.build_srt(shots), encoding="utf-8")
    (out_dir / "配音清单.md").write_text(
        core.build_dub_md(shots, title=title, character=character, style_name=style_name),
        encoding="utf-8", newline="\n"
    )
    compare_names = data.get("compare") or []
    if compare_names:
        md, page = core.build_compare(
            shots, title=title, styles=compare_names, aspect=aspect,
            character=character, duration=duration,
        )
        (out_dir / "多风格对比.md").write_text(md + "\n", encoding="utf-8", newline="\n")
        (out_dir / COMPARE_HTML).write_text(page, encoding="utf-8", newline="\n")

    meta = {
        "run_id": out_dir.name,
        "title": title,
        "character": character,
        "style": style_name,
        "aspect": aspect,
        "duration": duration,
        "shots": len(shots),
        "compare": compare_names,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    files = []
    for path in sorted(out_dir.iterdir()):
        if path.is_file():
            files.append({"name": path.name, "size": path.stat().st_size})
    preview = [
        {
            "no": shot["no"],
            "phase": shot["phase"],
            "duration": shot["duration"],
            "size": shot["size"],
            "move": shot["move"],
            "scene": shot["scene"],
            "dialogue": shot["dialogue"],
        }
        for shot in shots
    ]
    meta.update({"files": files, "shot_preview": preview, "html": PREVIEW_FILE})
    return meta
