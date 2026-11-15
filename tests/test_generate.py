"""生成平台适配层：provider 注册表、plan 预检、dry-run 提交与 job 契约。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project  # noqa: E402
from generate import (  # noqa: E402
    GenerateError,
    get_provider,
    job_detail,
    list_jobs,
    load_providers,
    plan,
    provider_ids,
    submit,
)
from generate.jobs import JobError, jobs_dir, read_job  # noqa: E402

PROMPT = "镜头：雨夜巷口，女人回头看向镜头，霓虹反光。\n" * 6


class GenerateProvidersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        report = create_project("生成适配", base=Path(self.tmp.name) / "projects")
        self.project = Path(report["path"])
        self.providers = load_providers()

    def test_load_providers(self) -> None:
        self.assertEqual(
            ["mock", "seedance_2_0", "seedance_2_5", "minimax_h3"],
            provider_ids(self.providers),
        )
        self.assertEqual("mock", get_provider("mock", self.providers)["kind"])
        self.assertEqual(
            ["seedance-2.5"], get_provider("seedance_2_5", self.providers)["models"]
        )
        with self.assertRaises(GenerateError):
            get_provider("nope", self.providers)

    def test_plan_rejects_unknown_model(self) -> None:
        provider = get_provider("seedance_2_0", self.providers)
        with self.assertRaises(GenerateError):
            plan(provider, self.project, prompt_text=PROMPT, model="seedance-9.9")

    def test_plan_rejects_overlong_prompt(self) -> None:
        provider = get_provider("seedance_2_0", self.providers)
        max_chars = int(provider["max_chars"])
        with self.assertRaises(GenerateError):
            plan(provider, self.project, prompt_text="长" * (max_chars + 1))

    def test_plan_requires_prompt(self) -> None:
        provider = get_provider("mock", self.providers)
        with self.assertRaises(GenerateError):
            plan(provider, self.project, prompt_text="", prompt_path=None)

    def test_plan_returns_limits_and_estimate(self) -> None:
        provider = get_provider("seedance_2_5", self.providers)
        result = plan(provider, self.project, prompt_text=PROMPT, shot="01")
        self.assertTrue(result["ok"])
        self.assertEqual("seedance-2.5", result["model"])
        self.assertEqual(len(PROMPT), result["chars"])
        self.assertEqual(64, len(result["prompt_sha256"]))
        self.assertEqual(30, result["limits"]["max_duration_s"])
        self.assertGreaterEqual(result["estimated"]["duration_s"], 3)

    def test_submit_platform_without_key_stays_dry_run(self) -> None:
        provider = get_provider("seedance_2_5", self.providers)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SEEDANCE_API_KEY", None)
            job = submit(self.project, provider, prompt_text=PROMPT, shot="02")
        self.assertTrue(job["dry_run"])
        self.assertEqual("dry_run", job["status"])
        self.assertTrue((jobs_dir(self.project) / f"{job['job_id']}.json").is_file())

    def test_submit_live_without_key_downgrades_to_dry_run(self) -> None:
        provider = get_provider("seedance_2_0", self.providers)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SEEDANCE_API_KEY", None)
            job = submit(
                self.project, provider, prompt_text=PROMPT, shot="", live=True
            )
        self.assertTrue(job["dry_run"])

    def test_mock_provider_always_dry_run(self) -> None:
        provider = get_provider("mock", self.providers)
        job = submit(self.project, provider, prompt_text=PROMPT, live=True)
        self.assertTrue(job["dry_run"])
        self.assertEqual("mock", job["provider"])

    def test_jobs_list_and_detail(self) -> None:
        provider = get_provider("mock", self.providers)
        first = submit(self.project, provider, prompt_text=PROMPT, shot="01")
        second = submit(self.project, provider, prompt_text=PROMPT, shot="03")
        jobs = list_jobs(self.project)
        self.assertEqual({first["job_id"], second["job_id"]}, {job["job_id"] for job in jobs})
        detail = job_detail(self.project, first["job_id"])
        self.assertEqual("01", detail["shot"])
        self.assertEqual("dry_run", detail["status"])

    def test_read_job_missing_raises(self) -> None:
        with self.assertRaises(JobError):
            read_job(self.project, "gen-20000101-000000-aaaaaa")


if __name__ == "__main__":
    unittest.main()
