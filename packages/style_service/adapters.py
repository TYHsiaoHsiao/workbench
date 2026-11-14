"""C 子系统：多模型提示词适配与结构校验。

设计原则：
- 只做结构校验（必填段落、禁用标记、时长/运镜约束），不评价创意质量；
- 规则版本化（v1），随提示词规范演进；
- 每个工具提供统一的风格注入块，便于 06 资产与 08 镜头复用。
"""
from __future__ import annotations

import re
from typing import Any

TOOL_IDS = (
    "mj",
    "banana",
    "seedance_2_0",
    "seedance_2_5",
    "h3",
    "sd",
    "runway",
    "pika",
)

IMAGE_TOOLS = ("mj", "banana", "sd")
VIDEO_TOOLS = ("seedance_2_0", "seedance_2_5", "h3", "runway", "pika")

TOOL_LABELS = {
    "mj": "Midjourney",
    "banana": "香蕉 / GPT-Image",
    "seedance_2_0": "Seedance 2.0",
    "seedance_2_5": "Seedance 2.5",
    "h3": "MiniMax H3",
    "sd": "Stable Diffusion",
    "runway": "Runway",
    "pika": "Pika",
}

TOOL_ALIASES = {
    "mj": "mj",
    "midjourney": "mj",
    "banana": "banana",
    "nano banana": "banana",
    "gpt-image": "banana",
    "seedance": "seedance_2_0",
    "seedance2": "seedance_2_0",
    "seedance_2_0": "seedance_2_0",
    "seedance 2.0": "seedance_2_0",
    "seedance2.0": "seedance_2_0",
    "seedance_2_5": "seedance_2_5",
    "seedance 2.5": "seedance_2_5",
    "seedance2.5": "seedance_2_5",
    "h3": "h3",
    "minimax": "h3",
    "minimax h3": "h3",
    "sd": "sd",
    "stable diffusion": "sd",
    "runway": "runway",
    "pika": "pika",
}

CONTINUITY_WORDS = ("上一镜头", "上一镜", "继续", "同上", "保持原样", "同前")

NEGATIVE_WORDS = ("不要", "禁止", "避免", "不能", "切勿")

CAMERA_MOVES = ("推近", "推镜", "拉远", "拉镜", "摇镜", "横移", "跟拍", "升镜", "降镜", "环绕", "手持", "固定镜头", "甩镜")

# v1 规范：required 字段需以文本片段出现；require_tokens 为必须包含的字面量；
# max_camera_moves 为区分的运镜种类上限；max_duration_seconds 为时长上限。
TOOL_SPECS: dict[str, dict[str, Any]] = {
    "mj": {
        "label": "Midjourney",
        "required": ("主体", "风格", "光线", "构图"),
        "require_tokens": ("--ar",),
        "forbid_negatives": False,
        "max_duration_seconds": None,
        "max_camera_moves": None,
        "max_chars": 6000,
    },
    "banana": {
        "label": "香蕉 / GPT-Image",
        "required": ("主体", "风格", "光线"),
        "require_tokens": (),
        "forbid_tokens": ("--",),
        "forbid_negatives": True,
        "max_duration_seconds": None,
        "max_camera_moves": None,
        "max_chars": 4000,
    },
    "seedance_2_0": {
        "label": "Seedance 2.0",
        "required": ("主体", "动作", "场景", "镜头", "光线"),
        "require_tokens": (),
        "forbid_negatives": False,
        "max_duration_seconds": 15,
        "max_camera_moves": 1,
        "max_chars": 3000,
    },
    "seedance_2_5": {
        "label": "Seedance 2.5",
        "required": ("整体", "光影", "镜头", "声音", "对白"),
        "require_tokens": (),
        "forbid_negatives": False,
        "max_duration_seconds": 30,
        "max_camera_moves": None,
        "max_chars": 5000,
    },
    "h3": {
        "label": "MiniMax H3",
        "required": ("画面", "镜头", "声音"),
        "require_tokens": ("overall_soundscape",),
        "forbid_negatives": False,
        "max_duration_seconds": 30,
        "max_camera_moves": None,
        "max_chars": 6000,
    },
    "sd": {
        "label": "Stable Diffusion",
        "required": ("Positive", "Negative"),
        "require_tokens": (),
        "forbid_negatives": False,
        "max_duration_seconds": None,
        "max_camera_moves": None,
        "max_chars": 4000,
    },
    "runway": {
        "label": "Runway",
        "required": ("主体", "镜头"),
        "require_tokens": (),
        "forbid_negatives": False,
        "max_duration_seconds": 10,
        "max_camera_moves": 1,
        "max_chars": 3000,
    },
    "pika": {
        "label": "Pika",
        "required": ("主体", "动作"),
        "require_tokens": (),
        "forbid_negatives": False,
        "max_duration_seconds": 10,
        "max_camera_moves": 1,
        "max_chars": 3000,
    },
}

DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒|s\b|sec\b)")


class AdapterError(ValueError):
    """工具名未知或规范不可用。"""


def _compact(text: str) -> str:
    return re.sub(r"[\s_\-.]+", "", text.strip().lower())


def normalize_tool(tool: str) -> str:
    key = str(tool or "").strip().lower()
    if key in TOOL_ALIASES:
        return TOOL_ALIASES[key]
    compact = _compact(key)
    for alias, canonical in TOOL_ALIASES.items():
        if _compact(alias) == compact:
            return canonical
    raise AdapterError(f"未知工具：{tool}（可用：{', '.join(TOOL_IDS)}）")


def stage_tools(stage: str) -> tuple[str, ...]:
    if stage == "06":
        return IMAGE_TOOLS
    if stage == "08":
        return VIDEO_TOOLS
    raise AdapterError(f"风格卡只挂载 06（图像资产）与 08（视频提示词），收到阶段 {stage}")


def tool_label(tool: str) -> str:
    return TOOL_LABELS.get(tool, tool)


def validate_prompt(tool: str, text: str) -> list[str]:
    """返回问题列表；空列表表示通过 v1 结构校验。"""
    canonical = normalize_tool(tool)
    spec = TOOL_SPECS[canonical]
    issues: list[str] = []
    body = (text or "").strip()
    if not body:
        return ["提示词为空"]
    max_chars = spec.get("max_chars")
    if max_chars and len(body) > max_chars:
        issues.append(f"长度超限：{len(body)} > {max_chars} 字符")
    for field in spec.get("required", ()):
        if field not in body:
            issues.append(f"缺少必填结构：{field}")
    for token in spec.get("require_tokens", ()):
        if token not in body:
            issues.append(f"缺少必需标记：{token}")
    for token in spec.get("forbid_tokens", ()):
        if token in body:
            issues.append(f"包含禁用标记：{token}")
    if spec.get("forbid_negatives"):
        for word in NEGATIVE_WORDS:
            if word in body:
                issues.append(f"该工具禁用否定式表达：{word}")
                break
    if canonical in VIDEO_TOOLS:
        for word in CONTINUITY_WORDS:
            if word in body:
                issues.append(f"视频提示词不得使用连续性指代：{word}")
    max_moves = spec.get("max_camera_moves")
    if max_moves is not None:
        moves = [move for move in CAMERA_MOVES if move in body]
        if len(moves) > max_moves:
            issues.append(f"运镜种类超限：{'、'.join(moves)}（上限 {max_moves} 种）")
        if max_moves >= 1 and not moves:
            issues.append("缺少运镜描述")
    max_duration = spec.get("max_duration_seconds")
    if max_duration is not None:
        for match in DURATION_RE.finditer(body):
            value = float(match.group(1))
            if value > max_duration:
                issues.append(f"时长超限：{value:g}s > {max_duration}s")
                break
    return issues


def palette_summary(profile: dict[str, Any]) -> str:
    parts = []
    for item in profile.get("palette", []):
        name = item.get("name", "")
        hex_value = item.get("hex", "")
        ratio = item.get("ratio", 0)
        parts.append(f"{name} {hex_value}（{ratio:g}%）")
    return "；".join(parts) if parts else "未提供调色板"


def style_block(profile: dict[str, Any], tool: str | None = None) -> str:
    """生成可注入提示词的风格卡文本块（纯文本，不含模型专属参数）。"""
    tool_line = ""
    if tool:
        canonical = normalize_tool(tool)
        tool_line = (profile.get("tool_adapters") or {}).get(canonical) or ""
    lines = [
        f"【风格卡】{profile.get('name', '')}（编号 {profile.get('director_no', '')}，分类 {profile.get('category', '')}）",
        f"色彩比例：{palette_summary(profile)}",
        f"光线：{profile.get('lighting', '')}",
        f"构图/镜头：{profile.get('lens', '')}",
    ]
    materials = profile.get("materials") or []
    if materials:
        lines.append(f"材质与色彩关键词：{'、'.join(materials)}")
    negatives = profile.get("negatives") or []
    if negatives:
        lines.append(f"禁止/避免：{'；'.join(negatives)}")
    if tool_line:
        lines.append(f"本工具适配：{tool_line}")
    return "\n".join(lines)


def combined_prompt(profile: dict[str, Any], tool: str, body: str) -> str:
    """风格块 + 用户提示词。风格块在前，正文在后，便于人工核对。"""
    canonical = normalize_tool(tool)
    return f"{style_block(profile, canonical)}\n\n{body.strip()}"
