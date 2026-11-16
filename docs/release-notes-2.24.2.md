# workbench 2.24.2 发行说明（CI 矩阵修正：移除 macOS）

- 类型：PATCH（无代码/契约变更）
- 内容：GitHub Actions 矩阵由 ubuntu/windows/macOS × Python 3.11/3.12 调整为 ubuntu/windows × Python 3.11/3.12（4 作业）。

## 背景

2.24.1 排除 `macos-latest + Python 3.12` 后，`macos-latest + Python 3.11` 作业仍多次排队约 15 分钟后被 GitHub 取消（无步骤输出），
导致 tag/分支 run 结论 failure；同 run 的 ubuntu/windows 作业全部成功。判断为当前环境 GitHub 托管 macOS runner 调度不可用，与代码无关。

## 变更

- `.github/workflows/ci.yml`：`os: [ubuntu-latest, windows-latest]`，共 4 个作业。
- 文档同步：`README.md`、`docs/ci.md`、`docs/github-actions.md`、`docs/command-card.md`、`docs/troubleshooting.md`。
- 无新增依赖、无契约变更。

## 验证

- 本地九步 CI 全 PASS。
- 远端：main/tag 推送后各 4 个作业应全部绿（ubuntu/windows × 3.11/3.12）。

## 升级

- 直接替换发行包即可；无数据/契约迁移。
