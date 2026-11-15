# 工作台 2.7.0（M19：需求追溯与 FR↔里程碑映射）

> 版本：2.7.0（MINOR，向后兼容）· 契约：v1.0（无变化）· 日期：2026-11-15

## 新增能力

- **需求追溯表**：`docs/requirements-traceability.md` 把 PRD §6 的 FR-01–FR-22 映射到
  实现位置（模块/命令/契约）、里程碑、验证证据与状态（已实现/部分实现/未实现），
  并附「扩展能力（M10–M19）」表与维护规则。
- **映射检查**：`scripts/check_fr_mapping.py` 校验追溯表覆盖 FR-01–FR-22、无重复与非预期 ID；
  若找到 PRD（默认仓库上一级 `AI影视工作台开发PRD.md`），再做标题集合交叉校验。
  已纳入 `scripts/run_ci.py`（编译 → 文档链接 → FR 映射 → 测试 → doctor → 基准 → 品牌守卫）。
- **CI 与文档**：命令卡新增映射检查命令；架构文档补 M19；PRD v2.17（§9.24 迭代 22、§6 追溯说明、§11.3 第 7 条门禁）。

## 验证

- 新增 `tests/test_ci_scripts.py::FrMappingTest` 4 项，全量 382 项通过。
- CI 七步全 PASS：FR 映射、文档链接检查、doctor、CLI 冷启动基准、品牌守卫 0 命中。
- `python scripts/check_fr_mapping.py`：22/22 FR 覆盖、PRD 交叉一致。

## 升级

- 解压 `dist/workbench-2.7.0.zip` 覆盖安装即可；本项目无运行时代码变化，无数据迁移。

## 限制

- 追溯表的状态口径为人工维护（与 PRD 同步），未实现项（如 FR-10 索引维护）仍需后续里程碑补齐。
- PRD 不在发行包内，CI 在仓库外无 PRD 时只校验覆盖（跳过交叉校验）。
