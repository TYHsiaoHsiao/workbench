# workbench 2.24.3 发行说明（2026-11-16）

## 概要

PATCH 补丁：修复远端 CI readiness 检查在 CI 矩阵移除 macOS 后误报失败的问题。

## 变更

- `scripts/ci_ready.py`：必需矩阵项改为 `ubuntu-latest` + `windows-latest`；`macos-latest` 改为可选，新增 `macos_present` 报告字段。
- `tests/test_ci_ready.py`：新增「无 macOS 工作流仍通过」用例；缺矩阵短语用例改为检测 `windows-latest`。
- `docs/ci.md`、`docs/github-actions.md`：补充矩阵要求与 macOS 可选说明。

## 验证

- 全量单元测试 525 项。
- 本地九步 CI（覆盖率、基准、品牌守卫、可复现构建）全部通过。
- 远端 GitHub Actions：ubuntu/windows × Python 3.11/3.12 四个作业。

## 兼容性

PATCH：无契约变更、无 CLI/API 破坏性变化；含 macOS 的工作流仍通过就绪检查。
