"""生成平台适配层：provider 注册表、plan 预检、dry-run 提交与 job 契约。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from core_router.project import create_project, load_state  # noqa: E402
from generate import (  # noqa: E402
    GenerateError,
    get_provider,
    job_detail,
    list_jobs,
    load_providers,
    plan,
    provider_ids,
    adopt,
    adopt_all,
    refresh,
    refresh_all,
    result_url,
    retry,
    submit,
)
from generate import providers as generate_providers  # noqa: E402
from generate.jobs import JobError, create_job, jobs_dir, read_job, update_job  # noqa: E402

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


class GenerateRefreshTest(unittest.TestCase):
    """M9：平台任务状态轮询（refresh / refresh_all / _http_status）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name) / "projects"
        report = create_project("刷新测试", base=base)
        self.project = Path(report["path"])
        self.prompt = self.project / "05_shots" / "shot-01-prompt.md"
        self.prompt.write_text(PROMPT, encoding="utf-8")
        self.providers = load_providers()

    def _submitted_job(
        self,
        provider: str = "seedance_2_5",
        model: str = "seedance-2.5",
        response: dict | None = None,
    ) -> dict:
        relative = str(self.prompt.relative_to(self.project))
        text = self.prompt.read_text(encoding="utf-8")
        job = create_job(
            self.project,
            provider=provider,
            model=model,
            project="刷新测试",
            shot="01",
            prompt_path=relative,
            prompt_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            chars=len(text),
            dry_run=False,
            status="submitted",
        )
        if response is not None:
            job = update_job(self.project, job["job_id"], response=response)
        return job

    def test_refresh_rejects_dry_run(self) -> None:
        provider = get_provider("mock", self.providers)
        job = submit(self.project, provider, prompt_text=PROMPT)
        with self.assertRaises(GenerateError) as ctx:
            refresh(self.project, job["job_id"])
        self.assertIn("dry-run", str(ctx.exception))

    def test_refresh_terminal_job_is_returned_unchanged(self) -> None:
        job = self._submitted_job()
        update_job(self.project, job["job_id"], status="succeeded")
        called = mock.Mock(side_effect=AssertionError("终态任务不应再查询平台"))
        result = refresh(self.project, job["job_id"], fetcher=called)
        called.assert_not_called()
        self.assertEqual("succeeded", result["status"])

    def test_refresh_running_keeps_submitted(self) -> None:
        job = self._submitted_job()
        result = refresh(
            self.project, job["job_id"], fetcher=lambda provider, job: {"status": "running"}
        )
        self.assertEqual("submitted", result["status"])

    def test_refresh_succeeded_records_platform_response(self) -> None:
        job = self._submitted_job(response={"id": "platform-1"})
        result = refresh(
            self.project,
            job["job_id"],
            fetcher=lambda provider, job: {
                "status": "succeeded",
                "video_url": "https://cdn.test/out.mp4",
            },
        )
        self.assertEqual("succeeded", result["status"])
        self.assertEqual("https://cdn.test/out.mp4", result["response"]["video_url"])

    def test_refresh_failed_records_error(self) -> None:
        job = self._submitted_job()
        result = refresh(
            self.project,
            job["job_id"],
            fetcher=lambda provider, job: {"status": "failed", "error": "content policy"},
        )
        self.assertEqual("failed", result["status"])
        self.assertIn("content policy", result["error"])

    def test_refresh_all_collects_results_and_tolerates_errors(self) -> None:
        first = self._submitted_job()
        second = self._submitted_job()
        dry = submit(self.project, get_provider("mock", self.providers), prompt_text=PROMPT)

        def fetcher(provider: dict, job: dict) -> dict:
            if job["job_id"] == second["job_id"]:
                raise GenerateError("平台超时")
            return {"status": "succeeded"}

        result = refresh_all(self.project, fetcher=fetcher)
        items = {item["job_id"]: item for item in result["refreshed"]}
        self.assertTrue(result["ok"])
        self.assertTrue(items[first["job_id"]]["ok"])
        self.assertEqual("succeeded", items[first["job_id"]]["status"])
        self.assertFalse(items[second["job_id"]]["ok"])
        self.assertIn("平台超时", items[second["job_id"]]["error"])
        self.assertNotIn(dry["job_id"], items)

    def test_http_status_builds_url_and_bearer_header(self) -> None:
        job = self._submitted_job(response={"id": "platform-123"})
        provider = get_provider("seedance_2_5", self.providers)
        captured: dict[str, object] = {}

        class FakeResponse:
            def __init__(self, payload: dict) -> None:
                self.payload = json.dumps(payload).encode("utf-8")

            def read(self) -> bytes:
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> bool:
                return False

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            return FakeResponse(
                {"status": "succeeded", "video_url": "https://cdn.test/x.mp4"}
            )

        with mock.patch.dict(
            os.environ,
            {"SEEDANCE_BASE_URL": "https://api.example.test", "SEEDANCE_API_KEY": "test-key"},
            clear=False,
        ):
            with mock.patch.object(generate_providers.urllib.request, "urlopen", fake_urlopen):
                payload = generate_providers._http_status(provider, job)
        self.assertEqual(
            "https://api.example.test/v1/video/generations/platform-123", captured["url"]
        )
        self.assertEqual("Bearer test-key", captured["auth"])
        self.assertEqual("succeeded", payload["status"])

    def test_http_status_requires_base_url(self) -> None:
        job = self._submitted_job(response={"id": "platform-123"})
        provider = get_provider("seedance_2_5", self.providers)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(GenerateError) as ctx:
                generate_providers._http_status(provider, job)
        self.assertIn("SEEDANCE_BASE_URL", str(ctx.exception))

    def test_http_status_requires_api_key(self) -> None:
        job = self._submitted_job(response={"id": "platform-123"})
        provider = get_provider("seedance_2_5", self.providers)
        with mock.patch.dict(
            os.environ, {"SEEDANCE_BASE_URL": "https://api.example.test"}, clear=True
        ):
            with self.assertRaises(GenerateError) as ctx:
                generate_providers._http_status(provider, job)
        self.assertIn("SEEDANCE_API_KEY", str(ctx.exception))


class GenerateRetryAdoptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        report = create_project("回填测试", base=Path(self.tmp.name) / "projects")
        self.project = Path(report["path"])
        self.prompt = self.project / "05_shots" / "shot-01-prompt.md"
        self.prompt.write_text(PROMPT, encoding="utf-8")

    def _job(
        self,
        *,
        status: str = "failed",
        dry_run: bool = False,
        response: dict | None = None,
        prompt_path: str | None = None,
    ) -> dict:
        relative = (
            str(self.prompt.relative_to(self.project))
            if prompt_path is None
            else prompt_path
        )
        text = self.prompt.read_text(encoding="utf-8")
        job = create_job(
            self.project,
            provider="seedance_2_5",
            model="seedance-2.5",
            project="回填测试",
            shot="01",
            prompt_path=relative,
            prompt_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            chars=len(text),
            dry_run=dry_run,
            status=status,
        )
        if status == "failed":
            job = update_job(self.project, job["job_id"], error="平台失败")
        if response is not None:
            job = update_job(self.project, job["job_id"], response=response)
        return job

    def test_retry_rejects_non_failed_job(self) -> None:
        job = self._job(
            status="succeeded", response={"video_url": "https://cdn.test/a.mp4"}
        )
        with self.assertRaises(GenerateError) as ctx:
            retry(self.project, job["job_id"])
        self.assertIn("failed / canceled", str(ctx.exception))

    def test_retry_creates_dry_run_job_with_retried_from(self) -> None:
        job = self._job()
        with mock.patch.dict(os.environ, {}, clear=True):
            new_job = retry(self.project, job["job_id"])
        self.assertNotEqual(job["job_id"], new_job["job_id"])
        self.assertEqual(job["job_id"], new_job["retried_from"])
        self.assertTrue(new_job["dry_run"])
        self.assertEqual("dry_run", new_job["status"])
        self.assertEqual("failed", job_detail(self.project, job["job_id"])["status"])

    def test_retry_live_override_keeps_dry_run(self) -> None:
        job = self._job(dry_run=True)
        with mock.patch.dict(os.environ, {}, clear=True):
            new_job = retry(self.project, job["job_id"], live=False)
        self.assertTrue(new_job["dry_run"])

    def test_retry_requires_prompt_path(self) -> None:
        job = self._job(prompt_path="")
        with self.assertRaises(GenerateError) as ctx:
            retry(self.project, job["job_id"])
        self.assertIn("没有提示词文件路径", str(ctx.exception))

    def test_adopt_requires_succeeded(self) -> None:
        job = self._job()
        with self.assertRaises(GenerateError) as ctx:
            adopt(self.project, job["job_id"])
        self.assertIn("只有 succeeded", str(ctx.exception))

    def test_adopt_writes_receipt_and_registers_artifact(self) -> None:
        url = "https://cdn.test/out.mp4"
        job = self._job(status="succeeded", response={"video_url": url})
        result = adopt(self.project, job["job_id"])
        artifact = result["artifact"]
        self.assertEqual(f"05_shots/generations/shot-01__{job['job_id']}.json", artifact)
        receipt_path = self.project / artifact
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(url, receipt["result_url"])
        self.assertEqual(url, result["result_url"])
        state = load_state(self.project)
        self.assertIn(artifact, state["stage_artifacts"]["05"])
        updated = job_detail(self.project, job["job_id"])
        self.assertEqual(artifact, updated["adopted"]["artifact"])

    def test_adopt_rejects_second_time(self) -> None:
        job = self._job(
            status="succeeded", response={"video_url": "https://cdn.test/b.mp4"}
        )
        adopt(self.project, job["job_id"])
        with self.assertRaises(GenerateError) as ctx:
            adopt(self.project, job["job_id"])
        self.assertIn("已回填过", str(ctx.exception))

    def test_adopt_requires_result_url(self) -> None:
        job = self._job(status="succeeded", response={"id": "platform-9"})
        with self.assertRaises(GenerateError) as ctx:
            adopt(self.project, job["job_id"])
        self.assertIn("没有可回填的结果 URL", str(ctx.exception))

    def test_result_url_extracts_nested_and_list(self) -> None:
        nested = {
            "response": {"data": {"outputs": [{"url": "https://cdn.test/nested.mp4"}]}}
        }
        self.assertEqual("https://cdn.test/nested.mp4", result_url(nested))
        listed = {"response": {"videos": ["https://cdn.test/list.mp4"]}}
        self.assertEqual("https://cdn.test/list.mp4", result_url(listed))
        self.assertEqual("", result_url({"response": None}))
        self.assertEqual("", result_url({}))

    def test_adopt_unknown_stage_rejected(self) -> None:
        job = self._job(
            status="succeeded", response={"video_url": "https://cdn.test/c.mp4"}
        )
        with self.assertRaises(GenerateError) as ctx:
            adopt(self.project, job["job_id"], stage="99")
        self.assertIn("未知阶段", str(ctx.exception))

    def test_adopt_all_skips_unsuitable_jobs(self) -> None:
        self._job(status="dry_run", dry_run=True)
        self._job()
        no_url = self._job(status="succeeded", response={"id": "platform-1"})
        result = adopt_all(self.project)
        self.assertEqual(0, result["adopted_count"])
        self.assertEqual(1, len(result["jobs"]))
        self.assertFalse(result["jobs"][0]["ok"])
        self.assertEqual(no_url["job_id"], result["jobs"][0]["job_id"])
        self.assertIn("没有可回填的结果 URL", result["jobs"][0]["error"])

    def test_adopt_all_adopts_succeeded_jobs_idempotently(self) -> None:
        first = self._job(
            status="succeeded", response={"video_url": "https://cdn.test/1.mp4"}
        )
        second = self._job(
            status="succeeded", response={"video_url": "https://cdn.test/2.mp4"}
        )
        result = adopt_all(self.project)
        self.assertEqual(2, result["adopted_count"])
        artifacts = {item["job_id"]: item["artifact"] for item in result["jobs"]}
        for job in (first, second):
            self.assertTrue((self.project / artifacts[job["job_id"]]).is_file())
            self.assertEqual(
                artifacts[job["job_id"]],
                job_detail(self.project, job["job_id"])["adopted"]["artifact"],
            )
        state = load_state(self.project)
        summary = state["stage_artifacts"]["05"]
        for job in (first, second):
            self.assertIn(artifacts[job["job_id"]], summary)
        again = adopt_all(self.project)
        self.assertEqual(0, again["adopted_count"])
        self.assertEqual([], again["jobs"])

    def test_adopt_all_stage_option(self) -> None:
        job = self._job(
            status="succeeded", response={"video_url": "https://cdn.test/6.mp4"}
        )
        result = adopt_all(self.project, stage="06")
        self.assertEqual(1, result["adopted_count"])
        artifact = result["jobs"][0]["artifact"]
        self.assertTrue(artifact.startswith("06_prompts/generations/"))
        self.assertIn("06_prompts/generations/", artifact)
        state = load_state(self.project)
        self.assertIn(artifact, state["stage_artifacts"]["06"])
        self.assertEqual(
            artifact, job_detail(self.project, job["job_id"])["adopted"]["artifact"]
        )


if __name__ == "__main__":
    unittest.main()
