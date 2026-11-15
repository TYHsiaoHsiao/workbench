# workbench 1.8.0 发行说明（M9：生成任务状态轮询与 Web 生成面板）

- 版本：1.8.0（契约 1.0，无契约变更）
- 日期：2026-11-15
- 范围：可视化节点工作台 M9——生成任务状态查询/刷新与 Web 生成面板

## 新增能力

### 任务状态查询（`packages/generate/providers.py`）

- `_http_status(provider, job)`：按 provider 的 `base_url_env` + `status_path`（默认 `/v1/video/generations/{job_id}`）GET 查询，`Authorization: Bearer <env_key>`；任务里的平台 id 从 response 中提取（`id` / `job_id` / `task_id` / `taskId` / `generation_id`）。
- 状态归一：平台响应统一映射为 `submitted` / `succeeded` / `failed`；无显式状态字段但含结果 URL 时视为 `succeeded`。
- `refresh(project_root, job_id)`：dry-run / mock / 终态任务直接拒绝或原样返回；其余查询后写回 `response` / `status` / `error`。
- `refresh_all(project_root, limit=20)`：只刷新非 dry-run 且状态为 `submitted` 的任务，单任务失败返回 `ok=false` 与错误文本，不影响其他任务。

### CLI

- `generate refresh <job_id> --project 项目名`：刷新单个任务。
- `generate refresh --all --project 项目名 [--limit 20]`：批量刷新 submitted 任务。
- 均支持 `--json`；缺少 `job_id` 且未给 `--all` 时按用法错误提示。

### Web API

- `GET /api/generate/providers`：每项新增 `env_set`（环境变量 key 是否已设置）。
- `POST /api/generate/jobs/<job_id>/refresh`：刷新单个任务，返回 `{ok, job}`。
- `POST /api/generate/jobs/refresh`：批量刷新，返回 `{ok, refreshed:[{job_id, ok, status, error?}]}`。
- 生成类错误统一转 400（`{ok:false, error}`）。

### Web 生成面板

- 顶栏新增「生成…」入口，overlay 面板包含：provider 表（kind/models/env 状态）、任务表（状态着色、submitted 任务可单条刷新）、预检（plan）/提交（默认 dry-run、勾选 live 需确认）/刷新全部。
- 任务列表按项目展示最近 30 条，可随时手动刷新。

## 验证

- `Ran 294 tests ... OK`（新增 11 项：状态查询 9、Web API 2）。
- CLI 冒烟：`generate refresh`（单任务与 `--all`）。
- Web API 冒烟：单任务刷新、批量刷新（mock 平台响应）。
- 本地 CI 全绿、品牌守卫 0 命中；`doctor` 9 项全 OK。

## 安全与限制

- 状态查询是**显式动作**，不后台自动轮询；需要 provider 的 `base_url_env`（如 `SEEDANCE_BASE_URL`）与 API key 环境变量，且网络可达。
- mock 与 dry-run 任务没有平台状态可查，刷新会被拒绝。
- 批量刷新只覆盖状态为 `submitted` 的任务；平台队列中的任务可能多次刷新后仍为 submitted。
- 只读查询、只写项目内任务记录；无契约变更，旧项目与流程图无需迁移。
