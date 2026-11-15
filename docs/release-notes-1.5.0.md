# 1.5.0 发行说明（M6：状态锁、运行对比、项目预览）

> 版本：1.5.0 · 日期：2026-11-15 · 契约：contracts 1.0（flow 系列 v0.1，均为可选字段扩展）

## 亮点

1. **写状态节点安全并行**：新增项目级文件锁与事务日志。知识检索、风格应用/注入、产物登记等写节点现在可在并行波次中运行，`state.json` 更新不再互相覆盖；事务记录见 `00_project/history/transactions.jsonl`。
2. **两次运行对比**：`flow diff` 与 Web API 按节点对齐两次运行的状态与耗时，标出回归/改善；适合调参与模板优化。
3. **项目摘要与预览**：`project summary` 与 Web 项目面板「预览」展示已登记产物、流程图结构（SVG 缩略图）与运行统计，可点击缩略图直接切换项目/流程。

## 使用

```bash
python workbench.py flow diff --project 我的短片 --run <run_id> --other-run <run_id>
python workbench.py project summary --project 我的短片 --json
python workbench.py project list --stats
```

Web：`flow serve --project ...` → 顶栏「项目」→「预览」；运行历史条目 → 打开回放 → 「对比」。

## 验证

- 新增 11 项测试（状态锁 5、运行对比 3、并行写锁集成 1、Web API 2），全量 247 项通过。
- 本地 CI 全绿（compile / tests / doctor / brand-guard），品牌守卫扫描 0 命中。
- CLI 冒烟：两次 dry-run → project summary → flow diff → project list --stats → doctor / flow validate 全部通过。

## 兼容与限制

- 契约版本不变（contracts 1.0；flow 系列 v0.1 新增字段均为可选），旧流程图与运行记录可直接使用。
- 状态锁仅对同一台机器上的进程有效，不支持跨机器并发写同一项目。
- 运行对比按 `node_id` 对齐，图结构大改时会出现 added/removed 噪声。
- 项目预览只读取已登记产物与 `00_project/workflows/` 下的图，不扫描未登记目录。

## 相关文档

- `docs/flow-workbench.md` §13（状态锁/运行对比/项目预览）、§15（验证）、§16（后续）。
- `docs/command-card.md`、`docs/troubleshooting.md`、`docs/architecture.md`。
