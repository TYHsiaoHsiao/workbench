# 2.13.1 发行说明（M26：远端 CI 工作流硬化与就绪检查）

## 能力

- `.github/workflows/ci.yml` 硬化：`permissions: contents: read`、`concurrency`（取消同分支旧运行）、`timeout-minutes: 30`、`PYTHONIOENCODING=utf-8`、artifact 保留 7 天，并新增 readiness 步骤。
- 新增 `scripts/ci_ready.py`：零依赖检查工作流矩阵/关键步骤与 `git remote`；`--require-remote` 供工作流使用；`--json` 可机读；本地无 remote 时仅提示不失败。
- 新增 `docs/github-actions.md`：接入步骤（remote/Actions 启用）、每作业内容、预期耗时、artifact、排障。
- 新增 `tests/test_ci_ready.py` 8 项测试。

## 验证

- 全量 **442 项测试通过**；`ci_ready.py` 本地检查通过（矩阵完整、remote 未配置为提示）。
- CI 九步全绿；覆盖率不变：行 80.84%、分支 50.52%。
- 本地无 git remote，远端矩阵为「待配置」状态（非失败）。

## 限制

- 真实远端执行需提供仓库地址并配置 remote；工作流自检为关键短语匹配，非严格 YAML 解析。
- 远端单作业耗时约 6–8 分钟（含约 5 分钟覆盖率/分支覆盖步骤）。

## 兼容性

- 无运行时行为变化、无契约变化；本地 CI 流程不变。
