# workbench 2.11.0 发行说明（M23：覆盖率提升与 80% CI 门禁）

日期：2026-11-15 · 版本：2.11.0（PATCH）· 契约：contracts v1.0（无变更）

## 1. 本版本能力

- **覆盖率达标**：`packages/` 行覆盖率由 77.37%（6017/7777）提升到 **80.8%（6284/7777）**，达到 PRD §7「核心逻辑测试覆盖 ≥80%」。
- **CI 门禁提升**：`scripts/run_ci.py` 覆盖率参数 `--min 75` → `--min 80`，覆盖率不达标即失败。
- **CLI 广覆盖测试**：新增 `tests/test_cli_coverage.py`，in-process 驱动更多子命令（项目快照/回滚、流程图导出导入、运行/回放/差异/基线、批次与恢复、队列定时/取消/重排/守护、索引构建与检索、generate 命令行）。
- **Web 错误路径测试**：新增 `test_http_error_paths`，覆盖未知 API 404、非法工作流/批次/队列/通知 400 与 HEAD 兜底。

## 2. 兼容性

- 无契约变更、无 CLI 参数变更、无破坏性行为变更；测试数量 413 → 420。

## 3. 验证

- 全量测试：`Ran 420 tests ... OK`
- 行覆盖率：80.8%（`scripts/coverage_check.py --min 80`）
- CI 九步全绿：compile / doc-links / fr-mapping / tests / coverage / doctor / bench / brand-guard / repro
- 打包冒烟与回滚演练（2.10.0 → 2.11.0 → 2.10.0）通过

## 4. 限制

- 覆盖率口径为行覆盖（非分支覆盖）；CLI 测试包含少量端到端流程，单测耗时略增。
- 后续新功能需维持 ≥80% 覆盖率，并逐步补分支覆盖。
