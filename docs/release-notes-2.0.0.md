# workbench 2.0.0 发行说明（M12：批次编排、批量自动重试与批次历史）

M12 在 M11 的基础上加入批量运行编排能力：`flow batch` 不再只是循环调用运行器，而是产出可追溯的批次记录，并支持失败图自动重试与批次历史查询。

## 能力

- **批次引擎**：新增 `packages/flow/batch.py` 与 `flow-batch` 契约（v0.1）。`run_batch()` 逐图运行（默认 dry-run、auto_confirm），批次记录写入 `00_project/workflows/batches/<batch_id>.json`；图级记录包含 `attempts`（每次尝试的 run_id/状态/耗时/错误）与 summary 统计。
- **自动重试**：`--auto-retry 0–3` 对失败图重跑（每次生成新 run_id，成功或进入 awaiting_confirm 即止）；`--fail-fast` 首个失败即停；`--limit` 限制图数量。
- **CLI**：`flow batch` 的 JSON 输出由 `{count,results}` 改为 `{ok,project,batch}`（破坏性变更）；新增 `--auto-retry`/`--fail-fast`/`--limit`，以及 `flow batches`、`flow batch-show` 两个查询命令。
- **Web API**：新增 `POST /api/workflows/batch`、`GET /api/batches`、`GET /api/batches/<batch_id>`；`POST /api/runs/batch` 保留为兼容别名（旧字段 `count`/`results`）。
- **前端**：批量预演改调新端点，逐图显示尝试次数、耗时与错误，完成状态包含批次 ID。
- **doctor**：flow 契约检查补 `flow-batch.schema.json`（共 5 份），contracts 共 14 份。

## 验证

- 新增 7 项测试（批次引擎 6：dry-run 批次记录/list/read、自动重试、fail_fast、limit、awaiting_confirm 会话、非法批次 ID；Web API 1：批次运行与历史查询），全量 `Ran 323 tests ... OK`。
- CLI 冒烟：`flow batch --all --dry-run`、`flow batches`、`flow batch --live --auto-retry 1`、`flow batch-show --json`；Web API 冒烟由 WebUI 测试覆盖。
- CI 全 PASS（compile/tests/doctor/brand-guard），doctor 9 项全 OK（contracts 14、flow 17 类/4 模板/5 契约）。

## 升级说明（2.0.0）

- `flow batch --json` 的结构是破坏性变更：请从 `batch.graphs` 读取每图结果；依赖旧 `results` 字段的脚本需调整（Web 兼容别名 `/api/runs/batch` 仍返回 `count`/`results`）。
- 除此之外，流程图、state v2、契约 v1.0、其他 CLI/Web 接口均无变化，旧项目无需迁移。

## 限制

- 批次逐图串行执行，暂不支持并行波次调度。
- 批次记录只保存图级汇总与尝试记录，不保存每次重试的完整运行详情；图校验失败的尝试不会生成运行记录。
- 自动重试是有限次数（0–3）的同步重跑，不含退避/排队等待；生成长任务请配合 generate 节点与显式刷新。
