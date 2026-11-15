"""生成任务存储（M8）。

任务记录写入项目内 ``00_project/generations/jobs/<job_id>.json``，契约校验后落盘；
默认 dry-run，只记录请求计划，不发起网络请求。
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import validate

CONTRACT_VERSION = "0.1"
JOB_SCHEMA = "generate-job.schema.json"
JOBS_DIR = Path("00_project") / "generations" / "jobs"


class JobError(Exception):
    """生成任务记录缺失或不符合契约。"""


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def jobs_dir(project_root: str | Path) -> Path:
    return Path(project_root) / JOBS_DIR


def new_job_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"gen-{stamp}-{secrets.token_hex(3)}"


def job_path(project_root: str | Path, job_id: str) -> Path:
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        raise JobError(f"非法任务 ID：{job_id!r}")
    return jobs_dir(project_root) / f"{job_id}.json"


def validate_job(job: dict[str, Any]) -> list[str]:
    return validate(job, schema_name=JOB_SCHEMA)


def write_job(project_root: str | Path, job: dict[str, Any]) -> Path:
    problems = validate_job(job)
    if problems:
        raise JobError("生成任务不符合契约：" + "；".join(problems))
    path = job_path(project_root, str(job.get("job_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_job(project_root: str | Path, job_id: str) -> dict[str, Any]:
    path = job_path(project_root, job_id)
    if not path.is_file():
        raise JobError(f"生成任务不存在：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise JobError(f"生成任务不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise JobError("生成任务根节点必须是对象")
    problems = validate_job(data)
    if problems:
        raise JobError("生成任务不符合契约：" + "；".join(problems))
    return data


def list_jobs(project_root: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, int(limit))
    directory = jobs_dir(project_root)
    if not directory.is_dir():
        return []
    jobs: list[dict[str, Any]] = []
    for path in directory.glob("gen-*.json"):
        try:
            jobs.append(read_job(project_root, path.stem))
        except JobError:
            continue
    jobs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return jobs[:limit]


def create_job(
    project_root: str | Path,
    *,
    provider: str,
    model: str,
    project: str,
    shot: str,
    prompt_path: str,
    prompt_sha256: str,
    chars: int,
    dry_run: bool,
    status: str = "planned",
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stamp = now()
    job: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "job_id": new_job_id(),
        "provider": provider,
        "model": model,
        "project": project,
        "shot": shot,
        "prompt_path": prompt_path,
        "prompt_sha256": prompt_sha256,
        "chars": int(chars),
        "status": status,
        "dry_run": bool(dry_run),
        "created_at": stamp,
        "updated_at": stamp,
    }
    if request:
        job["request"] = request
    write_job(project_root, job)
    return job


def update_job(project_root: str | Path, job_id: str, **fields: Any) -> dict[str, Any]:
    job = read_job(project_root, job_id)
    job.update({k: v for k, v in fields.items() if v is not None})
    job["updated_at"] = now()
    write_job(project_root, job)
    return job


__all__ = [
    "CONTRACT_VERSION",
    "JOB_SCHEMA",
    "JOBS_DIR",
    "JobError",
    "create_job",
    "job_path",
    "jobs_dir",
    "list_jobs",
    "new_job_id",
    "now",
    "read_job",
    "update_job",
    "validate_job",
    "write_job",
]
