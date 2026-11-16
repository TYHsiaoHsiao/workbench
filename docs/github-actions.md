# 远端 CI（GitHub Actions）

本页说明如何把 workbench 的本地 CI 接到 GitHub Actions 远端，以及矩阵、耗时、产物与排障。

## 1. 当前状态

- 工作流：`.github/workflows/ci.yml`（M26 硬化：`permissions: contents: read`、`concurrency` 取消旧运行、`timeout-minutes: 30`、`PYTHONIOENCODING=utf-8`、artifact 保留 7 天）。
- 矩阵：`ubuntu-latest` / `windows-latest` / `macos-latest` × Python `3.11` / `3.12`，共 6 个作业；当前排除 `macos-latest + 3.12`（runner 排队不稳定），实际 5 个作业。
- 触发：`push`、`pull_request`、`workflow_dispatch`。
- **真实远端执行的前提**：仓库已配置 git remote 且 Actions 已启用。本机当前 `git remote` 为空，本地只能验证工作流内容（`python scripts/ci_ready.py`），无法实际触发远端。

## 2. 接入步骤

```bash
cd workbench
git remote add origin <仓库地址>     # 例如 https://github.com/<owner>/<repo>.git
git push -u origin main
```

推送后在仓库 **Settings → Actions → General** 确认允许工作流运行。首次运行可用 **Actions → ci → Run workflow** 手动触发。

## 3. 就绪自检

```bash
python scripts/ci_ready.py              # 本地：工作流矩阵/步骤 + remote 提示
python scripts/ci_ready.py --require-remote   # 要求必须配置 remote（工作流内使用）
python scripts/ci_ready.py --json
```

工作流第一步即执行 `--require-remote`，因此远端环境下会校验 checkout 出来的 `origin` 是否存在。

## 4. 每个作业做什么

1. `ci_ready.py --require-remote`：工作流矩阵与 remote 自检。
2. `scripts/run_ci.py`：九步门禁（编译 → 文档链接 → FR 映射 → 测试 → 行/分支覆盖 → doctor → 冷启动基准 → 品牌守卫 → 可复现构建）。
3. `scripts/build_release.py`：生成 `dist/workbench-<版本>.zip` 与 `.sha256`。
4. `scripts/package_smoke.py`：SHA256 → 解压 → `version`/`doctor`/manifest 校验。
5. 上传 artifact：`workbench-<os>-py<版本>.zip`（保留 7 天）。

## 5. 预期耗时

- 单作业约 **6–8 分钟**（其中覆盖率步骤约 5 分钟：行覆盖 + 分支覆盖；三平台 6 作业并发）。
- 首次运行含环境初始化，可能略慢；`concurrency` 会取消同分支的旧运行。

## 6. 排障

- **Actions 没有运行**：确认默认分支、仓库 Settings 中 Actions 未禁用、`concurrency`/`permissions` 无权限问题。
- **Windows 作业中文乱码**：工作流已设置 `PYTHONIOENCODING=utf-8`；本地脚本读写统一 UTF-8。
- **覆盖率/分支覆盖失败**：先本地 `python scripts/run_ci.py` 复现；分支门禁 50%、行 80%。
- **artifact 缺失**：`dist/` 生成失败或 `if-no-files-found: error` 触发；查看 build_release 步骤日志。
- **当前无 remote**：本地 CI（`run_ci.py`）不受影响；远端执行只是**待配置**状态，不是失败。
