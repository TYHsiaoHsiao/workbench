# workbench 1.4.0 发行说明（M5）

> 发布日期：2026-11-15 · 契约版本：contracts 1.0 · 测试：236 项

## 1. 本版能力

- **并行分支执行**：执行引擎按拓扑深度分波；波内节点全部标记 `parallel_safe` 且图设置 `parallel=true` 时并发执行，其余情况串行。首版仅 `check_content` 与 `end` 并行安全，所有写 `state.json` 的节点保持串行，状态仍以 `state.json` 为唯一事实来源。
- **节点级重试**：节点可设 `retries`（0–3），图可设 `settings.node_retries`；执行器异常自动重试，步骤记录 `attempts` 与失败日志；`flow run --retries N` 覆盖默认。默认 0，避免写状态节点重复副作用。
- **项目管理面板**：Web 顶栏「项目」抽屉展示跨项目阶段/版本/待门禁/产物/流程图/运行/最近运行/更新时间，点击即可切换项目；CLI `project list --stats` 输出同源统计。
- **契约扩展**：`flow-run` step 增可选 `attempts`；`flow-graph` settings 增 `parallel`/`node_retries`、node 增 `retries`；`flow-node-types` 增 `parallel_safe`。均为向后兼容的可选字段。

## 2. 升级说明

- 无破坏性变更：契约 `contract_version` 仍为 `1.0`；旧流程图与运行记录仍可读取。
- 旧图默认 `parallel=false`、`node_retries=0`，行为与 1.3.0 完全一致。
- `doctor` 现为 8 项（新增 flow 检查：10 节点 / 4 模板 / 4 契约）；契约共 11 份。

## 3. 验证

| 项 | 结果 |
|---|---|
| 单元测试 | 236 项全部通过（新增 7 项：graph 3 / runner 3 / CLI 1 / Web 断言） |
| 本地 CI | compile / tests / doctor / brand-guard 全 PASS |
| 品牌守卫 | 扫描 0 命中 |
| CLI 冒烟 | init → flow new（模板）→ dry-run（attempts=1）→ project list --stats → doctor/validate 通过 |
| 发行包 | `dist/workbench-1.4.0.zip`（含 SHA-256） |

## 4. 已知限制

- 并行仅限只读节点；写状态节点的并发与依赖冲突留待后续版本（需引入锁或事务日志）。
- 重试对写状态节点可能重复副作用，默认关闭。
- 项目面板统计为只读聚合，不替代 `state.json`。
- macOS 实跑与 GitHub Actions 远端矩阵仍未启用。

## 5. 相关文档

- `docs/flow-workbench.md` §12 并行执行与节点级重试
- `docs/command-card.md`（`flow run --retries`、`project list --stats`）
- `docs/architecture.md` §9 可视化节点工作台
