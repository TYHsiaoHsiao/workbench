# workbench 2.24.1 发行说明（CI 矩阵补丁）

- 类型：PATCH（无代码/契约变更）
- 内容：远端 GitHub Actions 矩阵排除 `macos-latest + Python 3.12` 组合。

## 背景

2.24.0 推送后，两个 CI run 的 `test (macos-latest, py3.12)` 作业均在排队约 15 分钟后被 GitHub 取消（无任何步骤输出），
导致 run 结论 failure；同 run 的 `macos-latest, py3.11` 与 ubuntu/windows 作业全部成功。判断为 GitHub 托管 macOS runner 调度问题，与代码无关。

## 变更

- `.github/workflows/ci.yml`：矩阵新增 `exclude: [{os: macos-latest, python-version: "3.12"}]`，共 5 个作业；macOS 覆盖保留 3.11。
- 文档同步：`README.md`、`docs/ci.md`、`docs/github-actions.md`、`docs/command-card.md`、`docs/troubleshooting.md`。
- 无新增依赖、无契约变更。

## 验证

- 本地九步 CI 全 PASS（测试数与覆盖率与 2.24.0 相同）。
- 远端：推送后 tag/main 两个 run 应仅 5 个作业，且全部绿。

## 升级

- 直接替换发行包即可；无数据/契约迁移。
