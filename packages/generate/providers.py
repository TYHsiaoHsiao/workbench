"""生成平台 provider 注册表、请求计划与提交（M8）。

- 注册表：``content/generate-providers.json``（契约 ``generate-providers.schema.json``）。
- 计划：整理提示词、模型、字数与时长上限，返回可审阅的请求计划。
- 提交：默认 dry-run；仅当 ``live=True`` 且 provider 非 mock、环境变量存在时才发起 HTTP 请求。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from contracts import validate

from .jobs import JobError, create_job, list_jobs, now, read_job, update_job

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDERS_FILE = "generate-providers.json"
PROVIDERS_SCHEMA = "generate-providers.schema.json"
DEFAULT_PROVIDERS = REPO_ROOT / "content" / PROVIDERS_FILE
HTTP_TIMEOUT_S = 30
STAGE_DIRS = {
    "01": "01_story",
    "02": "02_script",
    "03": "03_assets",
    "04": "04_performance",
    "05": "05_shots",
    "06": "06_prompts",
    "07": "07_generations",
    "08": "08_delivery",
}


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


def _response_id(job: dict[str, Any]) -> str:
    """从任务记录的平台响应里取外部任务 ID。"""
    response = job.get("response")
    candidates: list[Any] = [response]
    if isinstance(response, dict):
        for key in ("data", "result"):
            if isinstance(response.get(key), dict):
                candidates.append(response[key])
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ("id", "job_id", "task_id", "taskId", "generation_id"):
            value = item.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
    return ""


def _payload_error(payload: dict[str, Any]) -> str:
    """从平台响应里提取可读错误信息。"""
    for key in ("error", "message", "msg", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = _payload_error(value)
            if nested:
                return nested
    for key in ("data", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            text = _payload_error(nested)
            if text:
                return text
    return ""


_SUCCESS_STATUS = {
    "succeeded", "success", "completed", "complete", "done", "finished",
    "ok", "成功", "已完成",
}
_FAILED_STATUS = {
    "failed", "failure", "error", "errored", "canceled", "cancelled",
    "rejected", "timeout", "失败", "已失败", "已取消",
}
_RUNNING_STATUS = {
    "queued", "pending", "running", "processing", "submitted", "in_progress",
    "in-progress", "waiting", "started", "排队中", "处理中", "生成中",
}
_RESULT_KEYS = ("video_url", "output_url", "result_url", "url", "video", "videos", "outputs")


def _has_result(payload: dict[str, Any]) -> bool:
    stack: list[Any] = [payload]
    while stack:
        item = stack.pop(0)
        if not isinstance(item, dict):
            continue
        for key in _RESULT_KEYS:
            value = item.get(key)
            if value:
                return True
        for key in ("data", "result"):
            if isinstance(item.get(key), dict):
                stack.append(item[key])
    return False


def _normalize_platform_status(payload: dict[str, Any]) -> str:
    """把平台状态归一为任务契约里的三种状态：submitted / succeeded / failed。"""
    state = ""
    stack: list[Any] = [payload]
    while stack:
        item = stack.pop(0)
        if not isinstance(item, dict):
            continue
        for key in ("status", "state", "task_status", "taskStatus", "phase"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                state = value.strip().lower()
                break
        if state:
            break
        for key in ("data", "result"):
            if isinstance(item.get(key), dict):
                stack.append(item[key])
    if state in _SUCCESS_STATUS:
        return "succeeded"
    if state in _FAILED_STATUS:
        return "failed"
    if state in _RUNNING_STATUS:
        return "submitted"
    if _has_result(payload):
        return "succeeded"
    return "submitted"


def _http_status(provider: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    base = os.environ.get(str(provider.get("base_url_env") or ""), "")
    if not base:
        raise GenerateError(
            f"缺少 {provider.get('base_url_env')} 环境变量，无法查询平台状态"
        )
    env_key = str(provider.get("env_key") or "")
    key = os.environ.get(env_key, "")
    if not key:
        raise GenerateError(f"缺少 {env_key} 环境变量，无法查询平台状态")
    template = str(provider.get("status_path") or "")
    if not template:
        raise GenerateError(
            f"provider {provider.get('provider_id')} 未配置 status_path"
        )
    external = _response_id(job) or str(job.get("job_id") or "")
    if not external:
        raise GenerateError(f"任务缺少可查询的平台 ID：{job.get('job_id')}")
    url = base.rstrip("/") + template.replace(
        "{job_id}", urllib.parse.quote(external, safe="")
    )
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise GenerateError(f"查询平台任务状态失败（{url}）：{exc}") from exc
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = {"raw": body[:2000]}
    return parsed if isinstance(parsed, dict) else {"response": parsed}


def refresh(
    project_root: str | Path,
    job_id: str,
    *,
    fetcher: Any | None = None,
) -> dict[str, Any]:
    """查询平台任务状态并更新本地任务记录。

    仅对非 dry-run、状态为 ``submitted`` 的任务有效；已终态任务原样返回。
    ``fetcher`` 仅供测试注入（签名 ``fetcher(provider, job) -> dict``）。
    """
    job = job_detail(project_root, job_id)
    if job.get("dry_run"):
        raise GenerateError(f"任务 {job_id} 是 dry-run 记录，没有平台状态可查询")
    current = str(job.get("status") or "")
    if current in ("succeeded", "failed", "canceled"):
        return job
    provider = get_provider(str(job.get("provider") or ""), load_providers())
    if provider.get("kind") == "mock":
        raise GenerateError(f"任务 {job_id} 使用 mock provider，没有平台状态可查询")
    fetch = fetcher or _http_status
    payload = fetch(provider, job)
    if not isinstance(payload, dict):
        raise GenerateError("平台状态响应必须是 JSON 对象")
    status = _normalize_platform_status(payload)
    fields: dict[str, Any] = {"response": payload}
    if status == "failed":
        fields["status"] = "failed"
        fields["error"] = _payload_error(payload) or "平台返回失败状态"
    elif status == "succeeded":
        fields["status"] = "succeeded"
    else:
        fields["status"] = "submitted"
    return update_job(project_root, job_id, **fields)


def refresh_all(
    project_root: str | Path, *, limit: int = 20, fetcher: Any | None = None
) -> dict[str, Any]:
    """刷新项目内所有 submitted 任务；单任务失败不影响其他任务。"""
    results: list[dict[str, Any]] = []
    for job in list_jobs(project_root, limit=limit):
        if job.get("dry_run") or str(job.get("status")) != "submitted":
            continue
        job_id = str(job.get("job_id"))
        try:
            updated = refresh(project_root, job_id, fetcher=fetcher)
        except (GenerateError, JobError) as exc:
            results.append(
                {
                    "job_id": job_id,
                    "ok": False,
                    "status": job.get("status"),
                    "error": str(exc),
                }
            )
            continue
        results.append({"job_id": job_id, "ok": True, "status": updated.get("status")})
    return {"ok": True, "refreshed": results}


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


def _first_result(payload: dict[str, Any]) -> str:
    stack: list[Any] = [payload]
    while stack:
        item = stack.pop(0)
        if not isinstance(item, dict):
            continue
        for key in _RESULT_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                for candidate in value:
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
                    if isinstance(candidate, dict):
                        for url_key in ("url", "video_url", "output_url"):
                            url = candidate.get(url_key)
                            if isinstance(url, str) and url.strip():
                                return url.strip()
        for key in ("data", "result"):
            if isinstance(item.get(key), dict):
                stack.append(item[key])
    return ""


def result_url(job: dict[str, Any]) -> str:
    """从任务 response 中提取第一个结果 URL（video_url 优先）。"""
    payload = job.get("response")
    if not isinstance(payload, dict):
        return ""
    return _first_result(payload)


def retry(
    project_root: str | Path, job_id: str, *, live: bool | None = None
) -> dict[str, Any]:
    """对 failed / canceled 任务按原 provider/模型/提示词创建新任务。

    ``live`` 为 None 时沿用原任务的提交方式（原任务真实提交则重试也真实提交；
    原任务是 dry-run 则重试仍为 dry-run）；显式传入 True/False 可覆盖。
    """
    job = job_detail(project_root, job_id)
    status = str(job.get("status") or "")
    if status not in ("failed", "canceled"):
        raise GenerateError(
            f"任务 {job_id} 当前状态为 {status}，只有 failed / canceled 任务可以重试"
        )
    prompt_path = str(job.get("prompt_path") or "")
    if not prompt_path:
        raise GenerateError(f"任务 {job_id} 没有提示词文件路径，无法重试")
    provider = get_provider(str(job.get("provider") or ""), load_providers())
    resolved_live = (not bool(job.get("dry_run"))) if live is None else bool(live)
    try:
        new_job = submit(
            project_root,
            provider,
            prompt_path=prompt_path,
            model=str(job.get("model") or "") or None,
            shot=str(job.get("shot") or ""),
            live=resolved_live,
        )
    except GenerateError as exc:
        raise GenerateError(f"重试任务 {job_id} 失败：{exc}") from exc
    try:
        return update_job(
            project_root, str(new_job["job_id"]), retried_from=job_id
        )
    except JobError as exc:
        raise GenerateError(f"重试任务记录更新失败：{exc}") from exc


def adopt(
    project_root: str | Path,
    job_id: str,
    *,
    stage: str = "05",
    kind: str = "generation",
    note: str = "",
) -> dict[str, Any]:
    """把 succeeded 任务的结果回填为项目产物。

    在 ``<阶段目录>/generations/`` 下写结果凭证 JSON（含任务快照与结果 URL），
    再通过 ``register_artifacts`` 登记进 ``state.stage_artifacts``，任务记录写入 ``adopted``。
    """
    job = job_detail(project_root, job_id)
    status = str(job.get("status") or "")
    if status != "succeeded":
        raise GenerateError(
            f"任务 {job_id} 当前状态为 {status}，只有 succeeded 任务可以回填结果"
        )
    if job.get("adopted"):
        raise GenerateError(
            f"任务 {job_id} 已回填过：{job['adopted'].get('artifact')}"
        )
    url = result_url(job)
    if not url:
        raise GenerateError(f"任务 {job_id} 的 response 中没有可回填的结果 URL")
    stage = str(stage or "05")
    directory = STAGE_DIRS.get(stage)
    if not directory:
        raise GenerateError(f"未知阶段：{stage}（可选 01-08）")
    shot = str(job.get("shot") or "").strip()
    name = f"shot-{shot}__{job_id}.json" if shot else f"{job_id}.json"
    name = re.sub(r"[^0-9A-Za-z._\u4e00-\u9fff-]", "_", name)
    root = Path(project_root)
    receipt = root / directory / "generations" / name
    receipt.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "job": job,
        "result_url": url,
        "adopted_at": now(),
        "note": note,
    }
    receipt.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    relative = receipt.relative_to(root).as_posix()
    from core_router.project import ProjectError, register_artifacts

    try:
        registered = register_artifacts(
            root, stage, kind, [relative], note=note or f"生成结果回填 {job_id}"
        )
    except ProjectError as exc:
        receipt.unlink(missing_ok=True)
        raise GenerateError(f"生成结果登记失败：{exc}") from exc
    try:
        updated = update_job(
            project_root, job_id, adopted={"artifact": relative, "at": now()}
        )
    except JobError as exc:
        raise GenerateError(f"回填任务记录更新失败：{exc}") from exc
    return {
        "ok": True,
        "job": updated,
        "artifact": relative,
        "result_url": url,
        "registered": registered,
    }


__all__ = [
    "DEFAULT_PROVIDERS",
    "GenerateError",
    "PROVIDERS_FILE",
    "PROVIDERS_SCHEMA",
    "STAGE_DIRS",
    "adopt",
    "get_provider",
    "job_detail",
    "load_providers",
    "plan",
    "provider_ids",
    "refresh",
    "refresh_all",
    "resolve_prompt",
    "result_url",
    "retry",
    "submit",
]
