# 发行说明 — workbench 1.0.0（2026-11-14）

首个正式版。1.0.0 之前已按迭代交付 A 编排硬化、B 知识接入、C 风格接入与试点验证；本版在此基础上补齐参考记忆加载、项目导出还原、试点实测与文档定稿，冻结契约版本 `contracts 1.0`。

## 一、能力总览

| 能力 | 状态 | 说明 |
|---|---|---|
| A 编排 | 正式 | 项目状态 v2、8 阶段注册表、门禁引擎、意图路由、安装器、迁移/升级、导出/还原 |
| B 知识 | 可用（方案 A） | 只读适配现有 `aistudio-md-2` 索引；元数据候选 + 有限正文回退 + 证据质量评分；不虚构命中 |
| C 风格 | 正式 | 200 位导演色卡注册表（A 140 / B 60 / C 0）；风格卡与 8 工具适配；06/08 显式注入与记录 |
| 质量守卫 | 正式 | 7 份契约 schema、品牌守卫、149 项测试、本地 CI 四步 |

## 二、相对 0.5.0 的变化

**新增**

- `core_router.memory`：参考记忆加载器（按阶段 scope 过滤 `enabled` 条目）+ CLI `reference list`；
- `core_router.project.export_project` / `restore_project`：项目 ZIP 导出（含元数据）与还原（拒绝路径穿越、拒绝覆盖非空目录）+ CLI `export` / `restore`；
- `scripts/pilot_matrix.py`：试点 A/B 自动化驱动与 M1–M9 指标采集；
- 文档定稿：`docs/command-card.md`、`docs/troubleshooting.md`、`docs/migration.md`、`docs/iteration-4-report.md`、`docs/quick-start.md`；
- 新增 8 项测试（memory 4、reference CLI 1、导出还原 3），合计 **149 项**。

**修复与改进**

- `memory_path` 修正为 `00_project/reference-memory.json`（首版遗漏 `00_project/`）；
- 试点中发现并修正：`style.apply/inject` 内部读写 state 导致本地状态陈旧覆盖门禁（改为服务调用后重新 `load_state`）、08 门禁通过后须先 `save_state` 再注入、mj 提示词必须带 `--ar`、注入记录键为 `record_sha256`；
- `build_manifest.py` 排除 `dist/`、`.pytest_cache/`，`.gitignore` 补齐缓存与 IDE 目录；
- 新增 `scripts/build_release.py`：可复现生成发行 ZIP 与 SHA-256。

## 三、验证结果

| 项 | 结果 |
|---|---|
| 全量测试 | **149 项通过**（`python -m unittest discover -s tests -v`） |
| 本地 CI | compile / tests / doctor / brand-guard 四项 PASS |
| 品牌守卫 | 扫描 183 个文件，**0 命中** |
| 契约 | 7 份 schema 全部校验通过，`contracts 1.0` |
| 试点 A | `试点A-雨夜回声`：01→02→04→05→06→07→08→done（v08），18/18 门禁一次通过 |
| 试点 B | `试点B-旧剧本接管`：停在 05（v04），作者剧本 SHA-256 前后一致（未改稿） |
| 回滚演练 | 从 `00_project/history/upgrade-*` 还原 `AGENTS.md`，哈希与备份一致 |

M1–M9：M1 100%、M2 11/11、M3 100%（负向拦截 4/4）、M4 平均 1.64 步/阶段、M5 100%、M6 100%、M7 0、M8 0、M9 P0/P1=0。

## 四、已知限制

1. **macOS 未实跑**：路径探测与命令已实现，E2E-02（macOS）标记为 skip；
2. **GitHub Actions 未远端首跑**：矩阵配置就绪；
3. **知识召回**：元数据 + 有限正文回退覆盖有限，完整召回与语义精度需方案 B（按契约重建索引）；
4. **迁移启发式**：复杂旧格式需按 `migration-report.md` 人工核对；
5. **参考记忆 MD 为视图**：`reference-memory.json` 才是唯一事实来源。

## 五、升级与兼容

- `contracts 1.0` 不变，0.5.0 项目可直接使用（建议先 `check --project <名>`）；
- 命令为增量新增，无破坏性改名；
- 旧项目（无 `state.json`）：`migrate` → `upgrade`，详见 `docs/migration.md`；
- 后续对契约做破坏性变更将升 2.x。

## 六、安装包与校验

发行包：`dist/workbench-1.0.0.zip`；校验文件：`dist/workbench-1.0.0.sha256`。
生成方式：`python scripts/build_release.py`（可复现）。
包内根目录为 `workbench/`，解压后按 `docs/quick-start.md` 操作。
