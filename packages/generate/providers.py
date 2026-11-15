"""生成平台 provider 注册表、请求计划与提交（M8）。

- 注册表：``content/generate-providers.json``（契约 ``generate-providers.schema.json``）。
- 计划：整理提示词、模型、字数与时长上限，返回可审阅的请求计划。
- 提交：默认 dry-run；仅当 ``live=True`` 且 provider 非 mock、环境变量存在时才发起 HTTP 请求。
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from contracts import validate

from .jobs import JobError, create_job, read_job, update_job

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDERS_FILE = "generate-providers.json"
PROVIDERS_SCHEMA = "generate-providers.schema.json"
DEFAULT_PROVIDERS = REPO_ROOT / "content" / PROVIDERS_FILE
HTTP_TIMEOUT_S = 30


class GenerateError(Exception):
    """生成平台配置、请求计划或提交失败。"""


def load_providers(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PROVIDERS
    if not target.is_file():
        raise GenerateError(f"生成平台注册表不存在：{target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GenerateError(f"生成平台注册表不是合法 JSON：{exc}") from exc
    problems = validate(data, schema_name=PROVIDERS_SCHEMA)
    if problems:
        raise GenerateError("生成平台注册表不符合契约：" + "；".join(problems))
    seen: set[str] = set()
    for item in data.get("providers") or []:
        provider_id = str(item.get("provider_id") or "")
        if provider_id in seen:
            raise GenerateError(f"生成平台 provider 重复：{provider_id}")
        seen.add(provider_id)
    return data


def _normalize(data: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return load_providers()
    if isinstance(data, dict):
        return data
    return load_providers(data)


def provider_ids(data: str | Path | dict[str, Any] | None = None) -> list[str]:
    payload = _normalize(data)
    return [str(item.get("provider_id")) for item in payload.get("providers") or []]


def get_provider(
    provider_id: str, data: str | Path | dict[str, Any] | None = None
) -> dict[str, Any]:
    payload = _normalize(data)
    for item in payload.get("providers") or []:
        if item.get("provider_id") == provider_id:
            return dict(item)
    raise GenerateError(
        f"未知生成平台：{provider_id}（可选：{', '.join(provider_ids(payload))}）"
    )


def _has_key(provider: dict[str, Any]) -> bool:
    env_key = str(provider.get("env_key") or "")
    return bool(env_key and os.environ.get(env_key))


def resolve_prompt(
    project_root: str | Path,
    *,
    prompt_text: str | None = None,
    prompt_path: str | None = None,
) -> tuple[str, str]:
    """返回 (提示词正文, 项目内相对路径)。两者都为空或同时给出时报错。"""
    if prompt_text and prompt_path:
        raise GenerateError("prompt_text 与 prompt_path 只能二选一")
    if prompt_text:
        text = str(prompt_text)
        if not text.strip():
            raise GenerateError("提示词为空")
        return text, ""
    if not prompt_path:
        raise GenerateError("未提供提示词：请给出 prompt_path 或 prompt_text")
    root = Path(project_root).resolve()
    path = Path(prompt_path)
    if not path.is_absolute():
        path = root / path
    try:
        path = path.resolve()
        relative = path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise GenerateError(f"提示词文件必须位于项目目录内：{prompt_path}") from exc
    if not path.is_file():
        raise GenerateError(f"提示词文件不存在：{relative.as_posix()}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise GenerateError(f"读取提示词失败：{exc}") from exc
    if not text.strip():
        raise GenerateError(f"提示词为空：{relative.as_posix()}")
    return text, relative.as_posix()


def plan(
    provider: dict[str, Any],
    project_root: str | Path,
    *,
    prompt_text: str | None = None,
    prompt_path: str | None = None,
    model: str | None = None,
    shot: str = "",
) -> dict[str, Any]:
    text, rel_path = resolve_prompt(
        project_root, prompt_text=prompt_text, prompt_path=prompt_path
    )
    models = [str(item) for item in provider.get("models") or []]
    chosen = str(model or (models[0] if models else ""))
    if not chosen:
        raise GenerateError(f"provider {provider.get('provider_id')} 未配置模型")
    if chosen not in models:
        raise GenerateError(
            f"模型 {chosen} 不在 provider {provider.get('provider_id')} 的模型列表：{', '.join(models)}"
        )
    chars = len(text)
    max_chars = provider.get("max_chars")
    if isinstance(max_chars, int) and chars > max_chars:
        raise GenerateError(f"提示词超长：{chars} 字 > 上限 {max_chars} 字")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    estimated: dict[str, Any] = {"chars": chars}
    max_duration = provider.get("max_duration_s")
    if isinstance(max_duration, int):
        suggested = max(3, min(max_duration, round(chars / 60)))
        estimated["duration_s"] = suggested
        estimated["duration_note"] = f"按约 60 字/秒估算，上限 {max_duration}s"
    dry_run = provider.get("kind") == "mock" or not _has_key(provider)
    return {
        "ok": True,
        "provider": provider.get("provider_id"),
        "label": provider.get("label"),
        "kind": provider.get("kind"),
        "model": chosen,
        "shot": shot,
        "chars": chars,
        "prompt_path": rel_path,
        "prompt_sha256": digest,
        "dry_run": dry_run,
        "limits": {
            "max_chars": max_chars,
            "max_duration_s": max_duration,
        },
        "estimated": estimated,
    }


def _http_submit(
    provider: dict[str, Any], *, model: str, prompt: str, shot: str, project: str
) -> dict[str, Any]:
    base = os.environ.get(str(provider.get("base_url_env") or ""), "")
    if not base:
        raise GenerateError(
            f"缺少 {provider.get('base_url_env')} 环境变量，无法提交真实请求"
        )
    env_key = str(provider.get("env_key") or "")
    key = os.environ.get(env_key, "")
    if not key:
        raise GenerateError(f"缺少 {env_key} 环境变量，无法提交真实请求")
    url = base.rstrip("/") + str(provider.get("submit_path") or "")
    payload = {
        "model": model,
        "prompt": prompt,
        "metadata": {"shot": shot, "project": project, "source": "workbench"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GenerateError(f"提交到 {url} 失败：{exc}") from exc
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = {"raw": body[:2000]}
    return parsed if isinstance(parsed, dict) else {"response": parsed}


def submit(
    project_root: str | Path,
    provider: dict[str, Any] | str,
    *,
    prompt_text: str | None = None,
    prompt_path: str | None = None,
    model: str | None = None,
    shot: str = "",
    live: bool = False,
) -> dict[str, Any]:
    data = _normalize(None)
    prov = get_provider(provider, data) if isinstance(provider, str) else dict(provider)
    planned = plan(
        prov,
        project_root,
        prompt_text=prompt_text,
        prompt_path=prompt_path,
        model=model,
        shot=shot,
    )
    from core_router.project import load_state

    state = load_state(project_root)
    project_name = str(state.get("project") or Path(project_root).name)
    dry_run = prov.get("kind") == "mock" or not live or not _has_key(prov)
    status = "dry_run" if dry_run else "submitted"
    request = {
        "model": planned["model"],
        "shot": shot,
        "dry_run": dry_run,
        "limits": planned["limits"],
        "estimated": planned["estimated"],
    }
    try:
        job = create_job(
            project_root,
            provider=str(prov.get("provider_id")),
            model=str(planned["model"]),
            project=project_name,
            shot=shot,
            prompt_path=str(planned["prompt_path"]),
            prompt_sha256=str(planned["prompt_sha256"]),
            chars=int(planned["chars"]),
            dry_run=dry_run,
            status=status,
            request=request,
        )
    except JobError as exc:
        raise GenerateError(f"生成任务记录失败：{exc}") from exc
    if dry_run:
        return job

    # 真实提交：任何失败都落成 failed 任务，保留证据，不抛出半成品。
    text, _ = resolve_prompt(
        project_root, prompt_text=prompt_text, prompt_path=prompt_path or None
    )
    job_id = str(job["job_id"])
    try:
        response = _http_submit(
            prov,
            model=str(planned["model"]),
            prompt=text,
            shot=shot,
            project=project_name,
        )
        job = update_job(
            project_root,
            job_id,
            status="submitted",
            response=response,
        )
    except GenerateError as exc:
        job = update_job(project_root, job_id, status="failed", error=str(exc))
        raise GenerateError(f"生成任务 {job_id} 提交失败：{exc}") from exc
    return job


def job_detail(project_root: str | Path, job_id: str) -> dict[str, Any]:
    try:
        return read_job(project_root, job_id)
    except JobError as exc:
        raise GenerateError(str(exc)) from exc


__all__ = [
    "DEFAULT_PROVIDERS",
    "GenerateError",
    "PROVIDERS_FILE",
    "PROVIDERS_SCHEMA",
    "get_provider",
    "job_detail",
    "load_providers",
    "plan",
    "provider_ids",
    "resolve_prompt",
    "submit",
]
