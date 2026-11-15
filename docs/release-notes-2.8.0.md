# workbench 2.8.0 发行说明（M20：跨平台 CI、覆盖率与可复现构建、Web 快照回滚）

> 版本：2.8.0 · 日期：2026-11-15 · 契约：contracts 1.0（无变更） · 范围：本地单用户

## 能力

### 1. 跨平台 CI 矩阵（`.github/workflows/ci.yml`）

- 触发：`push` / `pull_request` / `workflow_dispatch`。
- 矩阵：`ubuntu-latest`、`windows-latest`、`macos-latest` × Python `3.11`、`3.12`（6 作业）。
- 步骤：checkout → setup-python → `scripts/run_ci.py`（九步门禁）→ `scripts/build_release.py` → `scripts/package_smoke.py` → 上传 `dist/` 发行包 artifact。
- 本机无远端仓库，workflow 需推送 GitHub 后生效；本地等价命令为 `python scripts/run_ci.py`。

### 2. 覆盖率门禁（`scripts/coverage_check.py`）

- 零依赖行覆盖率：AST 收集 `packages/` 可执行行（跳过 docstring/纯 import），运行 `tests/` 并用 `sys.monitoring`（3.12+）或 `trace`（旧版本）统计。
- 实测 **76.37%（5590/7320 行）**；CI 以 `--min 75` 阻断。
- 与 PRD §7 的 80% 目标差 3.6pp，列入后续迭代提升项（§9.25）。

### 3. 可复现构建（`scripts/build_release.py` + `scripts/repro_check.py`）

- 发行包固定条目时间戳（1980-01-01）与权限（0o644），同一版本重复构建字节一致。
- `repro_check.py` 连续两次构建并与 `dist/workbench-<版本>.sha256` 三方比对，纳入 CI 第九步。

### 4. Web 快照与回滚面板

- API：`GET /api/rollback/snapshots?project=`、`POST /api/rollback/create`（`{project,label}`）、`POST /api/rollback/apply`（`{project,snapshot,dry_run}`）。
- 前端运行面板新增「创建快照」「快照列表」，列表行显示快照 ID、说明、时间、文件数与大小，可「回滚」或 dry-run 预演；回滚前自动创建安全快照。
- 复用 M18 的 `core_router.rollback`（快照落 `00_project/history/snapshots/`），Web 仅做调用与展示。

## 验证

- 全量 `Ran 387 tests ... OK`（新增 5 项：覆盖率 2、可复现构建 2、Web 回滚 1）。
- CI 九步全 PASS：doc-links、fr-mapping、tests、coverage（76.37%）、doctor、bench（冷启动中位数约 256ms）、brand-guard（275 文件 0 命中）、repro。
- 发行包 `dist/workbench-2.8.0.zip` 与 `.sha256` 一致；`package_smoke.py` 通过；`rollback_drill.py`（2.7.0→2.8.0→2.7.0）版本校验正确。
- Web 冒烟：`rollback create` → `GET /api/rollback/snapshots` → `apply --dry-run` → `apply` 恢复并生成安全快照。

## 使用

```bash
# 本地九步门禁（含覆盖率与可复现构建）
python scripts/run_ci.py

# 覆盖率报告 / 强制门禁
python scripts/coverage_check.py --json
python scripts/coverage_check.py --min 75

# 可复现构建校验
python scripts/repro_check.py --json

# Web 快照回滚
python workbench.py flow serve --project 预览演示 --port 8899
# 浏览器打开后 → 运行面板「创建快照」/「快照列表」/「回滚」
```

## 限制

- 覆盖率口径为行覆盖（非分支覆盖）；只统计 `packages/`。
- CI 矩阵目前仅定义未真实远端执行（本机无 remote）。
- 快照回滚为整文件覆盖，不做内容级合并；回滚后前端需手动刷新。
- Web 回滚不提供历史 diff 视图；快照清理/定时快照暂未实现。

## 兼容性

- 无契约变更、无 CLI 破坏性变更；新增 API 与脚本均为增量。
- 2.7.0 → 2.8.0 可直接替换发行包；回滚用 2.7.0 发行包并保留项目数据目录。
