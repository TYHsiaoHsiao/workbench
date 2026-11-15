# 发行说明 1.2.0 — 可视化节点工作台（M2 + M3）

> 发布日期：2026-11-15 · 契约：11 份（flow 系列 4 份，`contract_version` 均 0.1；其余契约仍 1.0） · 测试：222 项

## 本版重点

1. **能力节点（M2）**：节点类型从 4 类扩展到 10 类，新增 `knowledge_search`、`style_apply`、`style_inject`、`artifact_register`、`check_content`、`export`，与 `start` / `stage` / `confirm` / `end` 共同覆盖「知识检索 → 风格 → 阶段推进 → 内容体检 → 导出」全链路。
2. **模板库**：`content/flow-templates.json` 内置 4 套可复用流程——从零到成片（01→02→04→05→06→07→08）、B 入口接力（接管确认→05）、知识增强（检索→确认→01）、风格注入（apply→confirm）。新建流程图可 `--template` 一键实例化。
3. **运行历史与失败恢复**：每次运行持久化到 `00_project/workflows/runs/<run_id>.json`；`flow runs` 查看历史，`flow recover` 基于 `state_snapshot_before` 回滚后重跑（快照备份到 `00_project/history/`）。
4. **任意 DAG 与跳阶段（M3）**：`settings.allow_skip_stages` 将「前跳超过一个阶段」降级为警告，支持按需跳过可选阶段与自定义分支；图校验仍保证恰好一个 start、至少一个 end、无环、端口类型兼容。
5. **前端体验**：模板选择新建、撤销/重做（Ctrl+Z / Ctrl+Y，快照栈上限 60）、array/object 参数 JSON 编辑、运行历史面板、失败恢复按钮、批量预演、节点运行状态着色。
6. **统一内容检查**：`core_router/check.py` 抽出 `content_checks()`，CLI `check --content` 与 flow `check_content` 节点共用同一实现。

## 新增命令 / API

```bash
python workbench.py flow templates --json
python workbench.py flow new --project 我的短片 --template tpl-full-flow --name 从零到成片
python workbench.py flow runs --project 我的短片
python workbench.py flow batch --project 我的短片 --all --dry-run
python workbench.py flow recover --run <run_id> --project 我的短片 --yes [--restore-state]
```

- Web API：`GET /api/templates`、`GET /api/runs?project=&limit=`、`POST /api/runs/batch`、`POST /api/runs/<run_id>/recover`。
- `doctor` 增加 flow 模板检查（10 个节点类型、4 个模板、4 份契约）。

## 兼容与升级

- 升级方式：解压新发行包覆盖仓库或 `git pull` 后运行 `python scripts/run_ci.py`；`state.json` 与 8 阶段路由不变，已有项目无需迁移。
- `flow-run` 契约新增可选字段 `recovered_from` / `state_restored`，旧运行记录仍可读取。
- 已有 CLI 命令与参数全部保留，无破坏性变更。

## 验证

- 全量测试：`Ran 222 tests ... OK`（M1 204 + M2/M3 18：模板 6 / 能力节点 6 / runner 2 / Web API 4）。
- CLI 冒烟：模板实例化（tpl-knowledge 5 节点/4 连线）、dry-run（5 步 planned）、运行历史、批量预演、失败恢复（live 恢复后 01→02，知识卡 ok/候选 11/证据 8）。
- 本地 CI：compile / tests / doctor / brand-guard 全 PASS；品牌守卫扫描 221 文件 0 命中、跳过 4。
- 发行包：`dist/workbench-1.2.0.zip`（117 文件 / 395,571 字节），SHA256 见同目录 `.sha256`。

## 已知限制

- macOS 未实跑；GitHub Actions 远端矩阵尚未首次运行。
- 前端为原生实现，暂不支持多选批量移动、连线自定义路由、图模板导入/导出 UI。
- `flow recover` 会真实执行一次 live 运行（这是「恢复重跑」的语义），请先在 dry-run 下确认图。
- 节点执行仍是单进程串行；大规模批量运行未做并发优化。

## 相关文档

- `docs/flow-workbench.md`：节点、端口、模板、运行语义、API、前端交互、限制。
- `docs/command-card.md`：全部命令速查（含 flow 新命令）。
- `docs/troubleshooting.md` §14：可视化工作台常见问题。
