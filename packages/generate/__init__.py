"""生成平台适配层（M8）。

只做三件事：读取 provider 注册表、把提示词整理成请求计划、把请求落成可追踪的生成任务。
真实网络提交必须显式 ``live=True`` 且环境变量提供 key；否则一律降级为 dry-run 任务记录，
不发起网络请求、不产生费用。测试与 CI 只使用 ``mock`` provider。
"""

from __future__ import annotations

from .jobs import (
    JobError,
    create_job,
    job_path,
    jobs_dir,
    list_jobs,
    new_job_id,
    read_job,
    update_job,
    write_job,
)
from .providers import (
    PROVIDERS_FILE,
    PROVIDERS_SCHEMA,
    GenerateError,
    get_provider,
    job_detail,
    load_providers,
    plan,
    provider_ids,
    resolve_prompt,
    submit,
)

__all__ = [
    "GenerateError",
    "JobError",
    "PROVIDERS_FILE",
    "PROVIDERS_SCHEMA",
    "create_job",
    "get_provider",
    "job_detail",
    "job_path",
    "jobs_dir",
    "list_jobs",
    "load_providers",
    "new_job_id",
    "plan",
    "provider_ids",
    "read_job",
    "resolve_prompt",
    "submit",
    "update_job",
    "write_job",
]
