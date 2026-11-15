"""C 子系统：风格注册表（content/style-registry.json）的加载、校验与检索。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts import validate
from core_router.registry import REPO_ROOT

DEFAULT_REGISTRY = REPO_ROOT / "content" / "style-registry.json"
STYLE_REGISTRY_SCHEMA = "style-registry.schema.json"


class StyleRegistryError(RuntimeError):
    """风格注册表缺失、损坏或检索失败。"""


class StyleRegistry:
    """不可变风格注册表视图：按编号 / 英文名 / 中文名 / 目录解析。"""

    def __init__(self, data: dict[str, Any], path: Path) -> None:
        self.data = data
        self.path = path
        self.entries: list[dict[str, Any]] = list(data.get("entries", []))
        self.categories: list[dict[str, Any]] = list(data.get("categories", []))
        self._by_id = {entry["id"]: entry for entry in self.entries}

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, ref: str | int) -> dict[str, Any]:
        """按编号（001/1）、英文名、中文名或目录解析出唯一条目。"""
        entry = self._resolve(ref)
        if entry is None:
            raise StyleRegistryError(f"未找到风格：{ref}")
        return entry

    resolve = get

    def _resolve(self, ref: str | int) -> dict[str, Any] | None:
        raw = str(ref).strip()
        if not raw:
            return None
        digits = raw.zfill(3) if raw.isdigit() else ""
        if digits and digits in self._by_id:
            return self._by_id[digits]
        needle = raw.casefold()

        def names_of(entry: dict[str, Any]) -> list[str]:
            return [
                str(entry.get("name_en", "")),
                str(entry.get("name_zh", "")),
                str(entry.get("directory", "")),
            ]

        exact = [entry for entry in self.entries if any(name.casefold() == needle for name in names_of(entry) if name)]
        if len(exact) > 1:
            ids = "、".join(item["id"] for item in exact[:8])
            raise StyleRegistryError(f"风格名「{ref}」命中多个条目：{ids}；请改用编号")
        if exact:
            return exact[0]
        partial = [entry for entry in self.entries if any(needle in name.casefold() for name in names_of(entry) if name)]
        if len(partial) > 1:
            ids = "、".join(item["id"] for item in partial[:8])
            raise StyleRegistryError(f"风格名「{ref}」命中多个条目：{ids}；请改用编号")
        return partial[0] if partial else None

    def find(self, ref: str | int) -> dict[str, Any] | None:
        return self._resolve(ref)

    def list_entries(
        self,
        category: str | None = None,
        quality: str | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for entry in self.entries:
            if category and entry.get("category") != category.zfill(2):
                continue
            if quality and entry.get("quality") != quality.upper():
                continue
            result.append(
                {
                    "id": entry["id"],
                    "name_en": entry.get("name_en", ""),
                    "name_zh": entry.get("name_zh", ""),
                    "category": entry.get("category", ""),
                    "quality": entry.get("quality", ""),
                    "issues": len(entry.get("issues") or []),
                    "issue_labels": list(entry.get("issues") or []),
                }
            )
        return result

    def summary(self) -> dict[str, Any]:
        qc = self.data.get("qc") or {}
        return {
            "directors": len(self.entries),
            "categories": len(self.categories),
            "grade_counts": qc.get("grade_counts", {}),
            "duplicate_palettes": qc.get("duplicate_palettes", 0),
            "path": str(self.path),
        }


def load_style_registry(path: str | Path | None = None) -> StyleRegistry:
    registry_path = Path(path) if path else DEFAULT_REGISTRY
    if not registry_path.is_file():
        raise StyleRegistryError(f"风格注册表不存在：{registry_path}")
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StyleRegistryError(f"风格注册表 JSON 解析失败：{exc}") from exc
    errors = validate(data, schema_name=STYLE_REGISTRY_SCHEMA)
    if errors:
        raise StyleRegistryError("风格注册表校验失败：" + "；".join(errors[:5]))
    return StyleRegistry(data, registry_path)
