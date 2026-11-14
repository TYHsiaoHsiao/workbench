"""C 子系统：风格卡构建、阶段挂载与注入记录。

约束：
- 默认不注入：只有显式调用 style apply / style inject 才写项目文件；
- 注入必须通过 v1 结构校验；
- 不复制风格包素材，只引用编号、元数据与提示词结构。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from contracts import validate
from core_router.project import now

from . import adapters
from .registry import StyleRegistry, StyleRegistryError, load_style_registry

STYLE_CARD_DIR = "00_project/style-cards"
STYLE_PROFILE_SCHEMA = "style-profile.schema.json"

GENERIC_NEGATIVES = (
    "与参考作品完全一致的构图与调色",
    "水印、拼贴、文字叠加",
)


class StyleServiceError(RuntimeError):
    """风格卡构建、挂载或注入失败。"""


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        for sep in ("；", ";", "、", "，", ","):
            if sep in text:
                return [part.strip() for part in text.split(sep) if part.strip()]
        return [text]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _join(values: list[str], sep: str = "、") -> str:
    return sep.join(values)


def _style_profile(entry: dict[str, Any]) -> dict[str, Any]:
    profile = entry.get("style_profile") or {}
    return profile if isinstance(profile, dict) else {}


def _lighting_text(entry: dict[str, Any]) -> str:
    style = _style_profile(entry)
    palette = entry.get("palette") or {}
    lighting = palette.get("lighting") if isinstance(palette, dict) else None
    parts: list[str] = []
    if style.get("lighting"):
        parts.append(str(style["lighting"]))
    if isinstance(lighting, dict):
        for key in ("key_light", "overall_tone"):
            if lighting.get(key):
                parts.append(str(lighting[key]))
    return _join(parts, "；") or "按色卡主文档执行"


def _lens_text(entry: dict[str, Any]) -> str:
    style = _style_profile(entry)
    if style.get("framing"):
        return str(style["framing"])
    keywords = entry.get("keywords") or {}
    composition = keywords.get("composition") if isinstance(keywords, dict) else None
    if composition:
        return _join([str(item) for item in composition])
    return "按色卡主文档的构图关键词执行"


def _materials(entry: dict[str, Any]) -> list[str]:
    keywords = entry.get("keywords") or {}
    color = keywords.get("color") if isinstance(keywords, dict) else None
    mood = keywords.get("mood") if isinstance(keywords, dict) else None
    values = _as_list(color) + _as_list(mood)
    seen: list[str] = []
    for item in values:
        if item not in seen:
            seen.append(item)
    return seen[:12]


def _negatives(entry: dict[str, Any]) -> list[str]:
    avoid = _as_list(_style_profile(entry).get("avoid"))
    result = avoid or list(GENERIC_NEGATIVES)
    return result[:10]


def _tool_adapter_text(entry: dict[str, Any], tool: str) -> str:
    style = _style_profile(entry)
    definition = str(style.get("definition") or "按色卡主文档执行")
    parts = [f"{adapters.tool_label(tool)}：{definition}"]
    if style.get("grading"):
        parts.append(f"调色：{style['grading']}")
    if style.get("framing"):
        parts.append(f"构图：{style['framing']}")
    if tool in adapters.VIDEO_TOOLS:
        parts.append("运镜与节奏服从场次镜头规划")
    return "；".join(parts)


def build_profile(entry: dict[str, Any], tool: str | None = None) -> dict[str, Any]:
    """把注册表条目转换为 style-profile v1 契约对象。"""
    canonical = adapters.normalize_tool(tool) if tool else None
    palette = entry.get("palette") or {}
    primary = palette.get("primary") if isinstance(palette, dict) else None
    if not primary:
        raise StyleServiceError(f"风格 {entry.get('id')} 缺少调色板，无法生成风格卡")
    palette_items = []
    for item in primary:
        palette_items.append(
            {
                "name": f"{item.get('name_zh') or item.get('code', '色')}（{item.get('code', '')}）",
                "hex": item.get("hex", "#000000"),
                "ratio": float(item.get("ratio", 0)),
            }
        )
    category_name = entry.get("category_name") or entry.get("category") or ""
    tags = [str(item) for item in (category_name, entry.get("nationality", ""), entry.get("quality", "")) if str(item)]
    tags.append("色卡")
    adapters_map = {
        tool_id: _tool_adapter_text(entry, tool_id) for tool_id in adapters.TOOL_IDS
    }
    profile: dict[str, Any] = {
        "contract_version": "1.0",
        "profile_id": f"style-{entry['id']}" + (f"-{canonical}" if canonical else ""),
        "director_no": entry["id"],
        "name": f"{entry.get('name_zh') or entry.get('name_en') or entry['id']}"
        + (f" · {entry['name_en']}" if entry.get("name_en") else ""),
        "category": category_name,
        "tags": tags,
        "palette": palette_items,
        "lighting": _lighting_text(entry),
        "lens": _lens_text(entry),
        "materials": _materials(entry),
        "negatives": _negatives(entry),
        "tool_adapters": adapters_map,
        "quality": entry.get("quality", "B"),
    }
    errors = validate(profile, schema_name=STYLE_PROFILE_SCHEMA)
    if errors:
        raise StyleServiceError("风格卡校验失败：" + "；".join(errors[:5]))
    return profile


def apply_profile(
    project_root: str | Path,
    entry: dict[str, Any],
    tool: str | None = None,
) -> dict[str, Any]:
    from core_router.project import load_state, refresh_status_card, save_state

    root = Path(project_root)
    canonical = adapters.normalize_tool(tool) if tool else None
    profile = build_profile(entry, canonical)
    card_dir = root / STYLE_CARD_DIR
    card_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{canonical}" if canonical else ""
    card_path = card_dir / f"style-{entry['id']}{suffix}-profile.json"
    card_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = load_state(root)
    relative = card_path.relative_to(root).as_posix()
    state["style"] = {
        "status": "on",
        "profile_path": relative,
        "note": f"风格 {entry['id']} {entry.get('name_zh') or entry.get('name_en', '')}"
        + (f"；工具 {canonical}" if canonical else ""),
    }
    save_state(root, state)
    refresh_status_card(root)
    return {
        "ok": True,
        "style_id": entry["id"],
        "name": entry.get("name_zh") or entry.get("name_en", ""),
        "tool": canonical,
        "profile": profile,
        "card": str(card_path),
        "state": state["style"],
    }


def inject_prompt(
    project_root: str | Path,
    entry: dict[str, Any],
    stage: str,
    tool: str,
    prompt: str,
) -> dict[str, Any]:
    """把风格卡注入 06/08 提示词并写注入记录（严格结构校验）。"""
    from core_router.project import load_state

    root = Path(project_root)
    stage = str(stage)
    allowed = adapters.stage_tools(stage)
    canonical = adapters.normalize_tool(tool)
    if canonical not in allowed:
        raise StyleServiceError(
            f"阶段 {stage} 只允许 {', '.join(allowed)}；收到 {canonical}"
        )
    body = (prompt or "").strip()
    if not body:
        raise StyleServiceError("提示词为空")
    state = load_state(root)
    style_state = state.get("style") or {}
    profile_path = style_state.get("profile_path")
    if style_state.get("status") != "on" or not profile_path:
        raise StyleServiceError("项目尚未启用风格卡；请先运行 style apply")
    card_path = root / profile_path
    if not card_path.is_file():
        raise StyleServiceError(f"风格卡文件不存在：{card_path}")
    profile = json.loads(card_path.read_text(encoding="utf-8"))
    combined = adapters.combined_prompt(profile, canonical, body)
    # 结构校验针对用户正文：风格卡是固定元数据，其镜头语言不应挤占「一镜一运镜」名额
    issues = adapters.validate_prompt(canonical, body)
    if issues:
        raise StyleServiceError("提示词未通过结构校验：" + "；".join(issues))
    record_dir = root / STYLE_CARD_DIR
    record_dir.mkdir(parents=True, exist_ok=True)
    record_path = record_dir / f"style-{entry['id']}-injection-{stage}-{canonical}.json"
    record = {
        "contract_version": "1.0",
        "style_id": entry["id"],
        "style_name": entry.get("name_zh") or entry.get("name_en", ""),
        "stage": stage,
        "tool": canonical,
        "prompt_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "issues": [],
        "created_at": now(),
    }
    record_path.write_text(
        json.dumps({**record, "combined_prompt": combined}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    style_state["note"] = (
        f"风格 {entry['id']} {entry.get('name_zh') or entry.get('name_en', '')}"
        f"；最近注入 {stage}/{canonical}"
    )[:200]
    state["style"] = style_state
    from core_router.project import refresh_status_card, save_state

    save_state(root, state)
    refresh_status_card(root)
    return {
        "ok": True,
        "style_id": entry["id"],
        "stage": stage,
        "tool": canonical,
        "combined_prompt": combined,
        "record": str(record_path),
        "record_sha256": record["prompt_sha256"],
    }


class StyleService:
    """风格服务门面：注册表查询 + 风格卡 + 注入。"""

    def __init__(self, registry: StyleRegistry | None = None, registry_path: str | Path | None = None) -> None:
        try:
            self.registry = registry or load_style_registry(registry_path)
        except StyleRegistryError as exc:
            raise StyleServiceError(str(exc)) from exc

    def health(self) -> dict[str, Any]:
        return {
            "name": "style_service",
            "implemented": True,
            "target_iteration": "3",
            "directors": len(self.registry),
            "registry": str(self.registry.path),
        }

    def status(self) -> dict[str, Any]:
        return self.registry.summary()

    def get(self, ref: str | int) -> dict[str, Any]:
        try:
            return self.registry.get(ref)
        except StyleRegistryError as exc:
            raise StyleServiceError(str(exc)) from exc

    def list(self, category: str | None = None, quality: str | None = None) -> list[dict[str, Any]]:
        return self.registry.list_entries(category=category, quality=quality)

    def build(self, ref: str | int, tool: str | None = None) -> dict[str, Any]:
        return build_profile(self.get(ref), tool)

    def apply(self, project_root: str | Path, ref: str | int, tool: str | None = None) -> dict[str, Any]:
        return apply_profile(project_root, self.get(ref), tool)

    def inject(
        self,
        project_root: str | Path,
        ref: str | int,
        stage: str,
        tool: str,
        prompt: str,
    ) -> dict[str, Any]:
        return inject_prompt(project_root, self.get(ref), stage, tool, prompt)


__all__ = [
    "GENERIC_NEGATIVES",
    "STYLE_CARD_DIR",
    "STYLE_PROFILE_SCHEMA",
    "StyleService",
    "StyleServiceError",
    "apply_profile",
    "build_profile",
    "inject_prompt",
]
