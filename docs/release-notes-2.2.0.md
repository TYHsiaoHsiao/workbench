# workbench 2.2.0 发行说明（M14：批次队列化与失败通知）

- 版本：`2.2.0`（契约 `v1.0`；新增 `flow-queue` 契约 v0.1）
- 日期：2026-11-15
- 适用：本地单用户；零第三方运行时依赖，Python ≥ 3.10

## 一、能力

- 批次队列：每个项目维护 `00_project/workflows/queue.json`，`flow queue add` 把一次批量运行请求（图列表 + 参数）加入队列，条目初始 `pending`。
- 顺序执行：`flow queue run` 按创建顺序处理 pending 条目（默认最多 5 条），每条复用 `run_batch` 生成批次记录，并把批次 ID、结果汇总（成功/失败/尝试/耗时）写回条目。
- 失败通知：失败条目写 `notification.failed_graphs` 与 `message`，CLI 逐条打印、前端队列列表显示通知；成功条目保留 `result`。
- 跨项目队列：CLI `flow queue run --all-projects` 扫描默认项目根下所有项目依次执行。
- CLI：`flow queue add/list/run`（`--graphs`/`--all`、`--dry-run|--live`、`--auto-retry`、`--fail-fast`、`--parallel`、`--workers`、`--limit`、`--json`）。
- Web API：`POST /api/queue`、`POST /api/queue/run`、`GET /api/queue?project=&status=&limit=`。
- 前端：运行面板「加入队列」「运行队列」按钮；队列列表显示 queue_id/状态/图数/批次/失败通知（失败行红色）。
- doctor：flow 契约检查纳入 `flow-queue.schema.json`（6 份，contracts 共 15 份）。

## 二、验证

- 新增 10 项测试（队列引擎 8、Web API 2），全量 `Ran 341 tests ... OK`。
- CLI 冒烟：`flow queue add/list/run`（含 `--all-projects`）；Web API 队列端点冒烟。
- CI 全绿；品牌守卫 0 命中；doctor 9 项全 OK。

## 三、限制

- 队列串行执行、不做定时调度与后台守护；运行需显式 `flow queue run` / Web「运行队列」。
- 条目不会自动重试（可在入队时传 `--auto-retry`，由批次引擎重试失败图）。
- 队列文件位于项目目录内，跨进程并发队列不在支持范围；`--all-projects` 仅扫描默认项目根。

## 四、升级

- 直接替换发行包并运行 `python workbench.py doctor`；无需数据迁移。
- 旧项目第一次 `flow queue ...` 时自动创建空队列文件。
