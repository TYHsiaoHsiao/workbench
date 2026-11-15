# 工作台 2.6.0（M18：项目状态快照与回滚）

> 版本：2.6.0（MINOR，向后兼容）· 契约：v1.0（无变化）· 日期：2026-11-15

## 新增能力

- **项目状态快照**：`workbench.py rollback create --project <项目> [--label 标签]`
  将 `00_project/state.json`、参考记忆（JSON/MD）、`状态卡.md` 与 `00_project/workflows/**/*.json`
  （排除 `runs/`、`batches/`、`generations/`）打包为
  `00_project/history/snapshots/<snap-id>.zip`（含 metadata）。
- **回滚**：`workbench.py rollback apply --project <项目> --snapshot <snap-id> [--dry-run]`
  覆盖快照内文件并刷新状态卡；回滚前自动创建安全快照；`--dry-run` 只显示计划、不写盘；
  路径仅允许项目内 `00_project/` 或 `状态卡.md`，拒绝路径穿越；回滚写事务日志（action=rollback）。
- **快照列表**：`workbench.py rollback list --project <项目>`（创建时间倒序）。
- **发行包回滚演练**：`scripts/rollback_drill.py` 安装上一版 → 升级最新 → 回滚上一版，
  校验三者版本关系；支持 `--json`、`--keep`、`--workdir`。

## 验证

- 新增 `tests/test_rollback.py` 10 项，全量 378 项通过；`scripts/run_ci.py` 全 PASS
  （文档链接检查、doctor、CLI 冷启动基准、品牌守卫 0 命中）。
- 真实发行包演练：`workbench-2.4.0.zip` → `workbench-2.5.0.zip` → 回滚 `2.4.0`，版本均正确。

## 升级与回滚

- 安装：解压 `dist/workbench-2.6.0.zip` 到目标目录即可（零第三方依赖、Python ≥ 3.10）。
- 项目回滚：`rollback apply` 可回到任一已创建快照；回滚前自动安全快照，可再回滚回来。
- 版本回滚：保留上一版发行包，按 `scripts/rollback_drill.py` 的方式重新解压旧包验证版本。

## 限制

- 快照为全量文件保存，不做增量/去重；不覆盖外部只读目录（知识库/风格素材/10 Skills）。
- 暂无定时快照与快照清理策略（后续候选）。
