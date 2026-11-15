# 1.3.0 发行说明（可视化节点工作台 M4：运行回放与图导入导出）

> 版本：1.3.0 · 契约：workbench contracts 1.0（无破坏性变更）· 日期：2026-11-15

## 1. 本次新增

### 1.1 运行回放

- 新增 `packages/flow/replay.py`：把运行记录整理为时间线，包含每步节点、节点类型、状态、开始/结束时间、耗时、输出、错误与状态变更（`state_before` → `state_after`）。
- 汇总信息：总耗时、步骤耗时合计、最慢节点、失败节点与错误、恢复来源（`recovered_from`）。
- 入口：CLI `python workbench.py flow replay --project <项目> --run <run_id> [--json]`；Web API `GET /api/runs/<id>/replay`；前端在运行历史中点击条目打开回放抽屉（失败节点红色高亮，点击步骤跳转节点）。

### 1.2 流程图导入导出

- CLI：`flow export --project <项目> --graph <流程id> --out flow.json`（或 `--file flow.json` 原样输出）；`flow import --project <项目> --file flow.json [--graph 新id] [--force]`。
- Web API：`POST /api/workflows/import`（body 含 `project` 与 `graph`；非法图返回 HTTP 422 与错误列表）。
- 导入前复用 `validate_graph`（契约 + 语义 8 条规则），失败逐条报错且不落盘；导入成功后归一化 `graph_id` / `project` / `name`。

### 1.3 WebUI

- 顶栏新增「导出 / 导入」按钮（Blob 下载、文件选择上传）。
- 运行历史支持点击打开回放；历史条目内附「恢复」按钮，可携带状态快照回滚（`--restore-state` 等价）。

## 2. 命令与 API 变化

- 新增 CLI：`flow replay`、`flow export`、`flow import`。
- 新增 Web API：`GET /api/runs/<id>/replay`、`POST /api/workflows/import`。
- `flow` 包新增导出：`build_replay`、`format_replay_text`；`flow-run` 契约未变（回放是派生视图）。

## 3. 兼容性与升级

- 契约版本仍为 `1.0`，无破坏性变更；旧流程图、旧运行记录均可直接使用（缺时间戳的旧记录回放只给步骤序列）。
- 升级方式：替换发行包目录或按 `manifest.json` 校验文件；项目数据（`00_project/`、`state.json`、流程图与运行记录）无需迁移。

## 4. 验证

- 全量 `Ran 229 tests ... OK`（新增 `test_flow_replay` 5 项、Web API 回放/导入 2 项）。
- CLI 冒烟：模板图 → `flow run --dry-run` → `flow replay` → `flow export` → `flow import` → 非法导入被拒（exit 1）。
- 本地 CI：compile / tests / doctor / brand-guard 全 PASS；品牌守卫 0 命中。
- 发行包：`dist/workbench-1.3.0.zip` + `.sha256`（构建后核对）。

## 5. 已知限制

- 图与 state 为单向（图 → state），不支持从 state 反推流程图。
- 断点确认会话存于服务内存，服务重启后需重新运行。
- 回放耗时基于运行记录时间戳：串行节点精确，并行执行为近似。
- 图导出/导入只含流程图本身，不含项目状态与创作产物；跨项目迁移请用 `export` / `restore`。

## 6. 相关文档

- `docs/flow-workbench.md`（§11 回放与图导入导出）
- `docs/command-card.md`（§7 可视化节点工作流）
- `docs/troubleshooting.md`（§14 常见问题）
- `README.md`（迭代状态与快速开始）
