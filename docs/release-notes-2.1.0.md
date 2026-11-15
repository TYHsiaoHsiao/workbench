# workbench 2.1.0 发行说明（M13：批次并行预演与失败图恢复）

- **版本**：2.1.0（`VERSION`，MINOR：新增可选参数与可选契约字段，默认行为不变）
- **日期**：2026-11-15
- **范围**：渲染与流程编排层（`packages/flow`、`packages/generate` 不变、CLI/Web 前端、`flow-batch` 契约）

## 新增能力

### 批次并行预演

- `run_batch()` 与 `flow batch` 新增 `--parallel` / `--workers N`（1–8，默认 2）：使用线程池并行执行多个流程图，缩短批量预演时间。
- **仅支持 dry-run**：live 运行会共享项目状态（`00_project/state.json` 等），必须串行；`--parallel` 与 `--fail-fast` 互斥，违反时给出明确错误。
- 批次记录与 `flow-batch` 契约 v0.1 新增可选字段 `parallel`（bool）与 `workers`（1–8），旧记录仍可读取；`flow batches` / `flow batch-show` 摘要可看到并行设置。

### 失败图一键恢复

- 新增 `recover_batch(project_root, batch_id)`：只重跑原批次中 `ok=false` 的失败图，把新尝试追加到原批次的 `attempts` 链（编号接续），合并后重算 `status`/`summary`（成功图与跳过图保留，总时长为各图时长之和）。
- CLI：`python workbench.py flow batch-recover --project 项目 --batch <batch_id> [--dry-run/--live] [--auto-retry N] [--parallel] [--workers N] [--json]`。
- Web：`POST /api/batches/<batch_id>/recover`；前端批量预演后若有失败图，自动显示「恢复失败图」按钮，恢复完成后刷新批次状态与历史。
- 无失败图时返回 `recovered=0`，不写空更新。

## 验证

- 新增 6 项测试：
  - 批次引擎 4 项：并行 dry-run 落盘、并行拒绝 live 与 fail-fast、恢复合并尝试链、无失败恢复返回 0；
  - Web API 2 项：并行批次端点、恢复端点。
- 全量测试：`Ran 331 tests ... OK`（原 325 + 6）。
- CLI 冒烟：`flow batch --all --dry-run --parallel --workers 2`、`flow batch-recover --batch <id>`（失败图重跑并合并尝试）。
- `doctor`：9 项自检通过（contracts 14、flow 17 类节点/4 模板/5 契约）。
- 品牌守卫与 CI：全 PASS。

## 兼容性与升级

- 批次记录的 `parallel`/`workers` 为可选字段，旧批次记录与旧调用方无需改动；默认串行，`flow batch` 不带 `--parallel` 时行为与 2.0.1 相同。
- 恢复机制复用原批次记录（不产生新批次），如需独立记录可再执行一次 `flow batch`。

## 已知限制

- 并行仅用于 dry-run 预演；live 必须串行。
- 恢复按图整体重跑，不从中途断点继续；恢复后仍失败的图可修复后再次恢复。
- 批次记录文件位于 `00_project/workflows/batches/`，未纳入导出/恢复（`project export`）清单。
