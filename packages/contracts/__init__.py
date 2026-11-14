"""契约层：加载 JSON Schema 并提供标准库实现的最小校验器。

不引入第三方依赖（PRD 非目标：不新增运行时依赖）；校验器只覆盖本项目需要的
JSON Schema 子集，遇到未知关键字会忽略而不是报错，以保证 schema 可渐进扩展。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
CONTRACT_VERSION = "1.0"

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def list_schemas() -> list[str]:
    """返回内置 schema 文件名（不含目录）。"""
    return sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json"))


def load_schema(name: str) -> dict[str, Any]:
    """按文件名加载 schema；name 可带或不带 .json 后缀。"""
    filename = name if name.endswith(".json") else f"{name}.schema.json"
    path = SCHEMA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"schema 不存在: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_type(value: Any, expected: str) -> bool:
    if expected == "number":
        return _is_number(value)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    cls = _TYPE_MAP.get(expected)
    if cls is None:
        return True
    if expected == "boolean":
        return isinstance(value, bool)
    return isinstance(value, cls) and not (
        expected in ("string", "object", "array") and False
    ) and not (expected != "boolean" and isinstance(value, bool) and expected == "integer")


def _pointer(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    if not path or path == "$":
        return f"$.{key}"
    return f"{path}.{key}"


def validate(instance: Any, schema: dict[str, Any] | None = None,
             schema_name: str | None = None, path: str = "$") -> list[str]:
    """校验实例，返回错误列表（空列表表示通过）。

    schema 与 schema_name 二选一；错误格式统一为 ``$.path: message``。
    """
    if schema is None:
        if schema_name is None:
            raise ValueError("必须提供 schema 或 schema_name")
        schema = load_schema(schema_name)
    errors: list[str] = []
    _validate(instance, schema, path, errors)
    return errors


def _validate(instance: Any, schema: Any, path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict):
        return

    const = schema.get("const")
    if const is not None and instance != const:
        errors.append(f"{path}: 应为常量 {const!r}，实际 {instance!r}")
        return

    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        errors.append(f"{path}: 取值必须是 {enum!r} 之一，实际 {instance!r}")

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_check_type(instance, t) for t in expected_types):
            errors.append(f"{path}: 类型应为 {expected_type!r}，实际 {type(instance).__name__}")
            return

    if isinstance(instance, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in instance:
                errors.append(f"{_pointer(path, key)}: 缺少必填字段")
        properties = schema.get("properties") or {}
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], _pointer(path, key), errors)
            elif additional is False:
                errors.append(f"{_pointer(path, key)}: 不允许的额外字段")
    elif isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(instance):
                _validate(value, items, _pointer(path, index), errors)
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            errors.append(f"{path}: 至少需要 {min_items} 个元素，实际 {len(instance)}")
    elif isinstance(instance, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            errors.append(f"{path}: 长度至少 {min_length}，实际 {len(instance)}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            errors.append(f"{path}: 不匹配模式 {pattern!r}")
    elif _is_number(instance):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if _is_number(minimum) and instance < minimum:
            errors.append(f"{path}: 不得小于 {minimum}，实际 {instance}")
        if _is_number(maximum) and instance > maximum:
            errors.append(f"{path}: 不得大于 {maximum}，实际 {instance}")
    elif isinstance(instance, bool):
        pass


def validate_file(path: str | Path, schema_name: str) -> list[str]:
    """读取 JSON 文件并校验。"""
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return validate(data, schema_name=schema_name)
