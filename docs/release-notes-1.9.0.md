# 1.9.0 发行说明（M10：生成结果回填、失败重试与任务详情抽屉）

> 版本：workbench 1.9.0 · 契约：1.0（`generate-job` 增加可选字段）· 发布：2026-11-15

## 本次新增

- **结果回填**：`generate adopt <job_id> --project <项目> [--stage 05] [--kind generation] [--note 备注]`；仅 succeeded 且未回填的任务可回填。在 `<阶段目录>/generations/shot-XX__<job_id>.json` 写结果凭证（任务快照 + result_url + adopted_at + note），经 `register_artifacts` 登记 `state.stage_artifacts`，任务记录写入 `adopted`。
- **失败重试**：`generate retry <job_id> --project <项目> [--live | --dry-run]`；仅 failed/canceled 可重试，按原 provider/模型/提示词创建新任务并记录 `retried_from`；默认沿用原任务提交方式，可显式覆盖。
- **Web API**：`POST /api/generate/jobs/<job_id>/retry`（body: project / live）与 `POST /api/generate/jobs/<job_id>/adopt`（body: project / stage / kind / note）。
- **任务详情抽屉**：生成面板任务表每行「详情」打开抽屉，展示 provider/模型/状态/镜头/提示词/字数、重试来源、回填结果、错误信息与任务 JSON；failed 显示「重试」、succeeded 未回填显示「回填」、已回填显示结果产物路径。
- **契约**：`generate-job` 增加可选 `retried_from`（`^gen-[a-z0-9-]{6,60}$`）与 `adopted`（`artifact`+`at`），向后兼容。

## 验证

- 新增 12 项测试（重试/回填 10、Web API 2）；全量 `Ran 306 tests ... OK`。
- 本地 CI：compile / tests / doctor（9 项）/ brand-guard 全部 PASS，品牌守卫 0 命中。
- CLI 冒烟：`generate retry`、`generate adopt`；Web 冒烟：生成面板任务详情、重试、回填。
- 发布包：`dist/workbench-1.9.0.zip`（含 SHA-256 校验文件）。

## 使用示例

```text
python workbench.py generate refresh <job_id> --project 我的短片          # 1) 先刷新为 succeeded
python workbench.py generate adopt <job_id> --project 我的短片 --stage 05  # 2) 回填到 05_shots/generations/
python workbench.py generate retry <failed_job_id> --project 我的短片     # 失败任务重试（默认沿用原提交方式）
```

## 限制与兼容

- 回填只登记结果凭证 JSON（含平台结果 URL），不下载/转存平台视频文件。
- 重试不会自动退避或轮询，需要时再 `generate refresh`。
- 真实提交与状态查询需要对应 provider 的 `base_url_env` / `env_key` 与网络；mock 与 dry-run 无平台状态。
