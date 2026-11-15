# CI、跨平台矩阵与可复现构建（M20 / 2.8.0）

> 版本：2.8.0 · 适用：本地与 GitHub Actions · 维护：`scripts/run_ci.py`

本页说明工作台的 CI 门禁、跨平台矩阵、本地等价命令、覆盖率策略与可复现构建。

## 1. 九步门禁（`python scripts/run_ci.py`）

| 步骤 | 检查 | 失败含义 |
|---|---|---|
| compile | `python -m compileall` 编译 `packages/`、`scripts/`、`workbench.py` | 语法错误 |
| doc-links | `scripts/check_doc_links.py` | Markdown/行内代码引用了不存在的仓库路径 |
| fr-mapping | `scripts/check_fr_mapping.py` | 需求追溯表缺 FR / 重复 / 与 PRD §6 不一致 |
| tests | `python -m unittest discover -s tests` | 单元/契约/集成测试失败 |
| coverage | `scripts/coverage_check.py --min 80` | 行覆盖率低于 80% |
| doctor | `python workbench.py doctor` | 环境/契约/注册表自检失败 |
| bench | `scripts/bench.py --enforce --max-cold-start 1.0` | CLI 冷启动 P50 超过 1.0s |
| brand-guard | `python workbench.py brand-guard` | 品牌禁用词命中 |
| repro | `scripts/repro_check.py` | 两次构建 SHA256 不一致或与 `.sha256` 不符 |

任一失败即非零退出，CI 阻断。

## 2. GitHub Actions 跨平台矩阵

`.github/workflows/ci.yml`：

- 触发：`push`、`pull_request`、`workflow_dispatch`。
- 矩阵：`ubuntu-latest` / `windows-latest` / `macos-latest` × Python `3.11` / `3.12`，共 6 个作业。
- 步骤：`actions/checkout@v4` → `actions/setup-python@v5` → `python scripts/run_ci.py` → `python scripts/build_release.py` → `python scripts/package_smoke.py` → `actions/upload-artifact@v4`（`dist/workbench-*.zip` 与 `.sha256`）。

> 本仓库默认无远端（`git remote -v` 为空），workflow 需推送到 GitHub 后才执行；本地等价入口是 `scripts/run_ci.py`。

## 3. 本地等价命令

```bash
python scripts/run_ci.py                     # 九步门禁
python scripts/coverage_check.py --json      # 行覆盖率报告（机器可读）
python scripts/coverage_check.py --min 80    # 强制门禁
python scripts/repro_check.py --json         # 可复现构建校验
python scripts/build_release.py              # 生成发行包与 .sha256
python scripts/package_smoke.py              # 发行包冒烟
```

## 4. 覆盖率策略

- 测试对象：`packages/`（`workbench.py` 为 6 行入口，不计入，避免 0% 稀释）。
- 口径：AST 可执行行（跳过 docstring、纯 `import`），运行 `tests/` 时用 `sys.monitoring`（Python 3.12+）或 `trace`（旧版本）统计命中行。
- 实测（2.12.0）：**80.84%**，CI 门禁 `--min 80`。
- 与 PRD 目标：PRD §7 要求测试覆盖率 ≥80%，2.12.0 实测 80.84%，**已达标**；新增代码必须带测试，覆盖率只增不减。

## 5. 可复现构建

- `scripts/build_release.py` 固定 zip 条目时间戳为 `1980-01-01 00:00:00`、文件权限归一为 `0o644`、条目按清单顺序写入。
- `scripts/repro_check.py` 连续构建两次并比对：两次 zip 的 SHA256 必须一致，且与 `dist/workbench-<版本>.sha256` 记录一致。
- 因此同一版本在不同机器/时间构建应得到相同字节（仅依赖 Python 版本相关的 `zlib` 压缩实现；CI 矩阵覆盖 3.11/3.12）。

## 6. 常见问题

- **覆盖率报错但测试全过**：`coverage_check.py` 只统计 `packages/` 且跳过 docstring/import；看 `--json` 中 `files` 的 `percent` 排序，优先补低覆盖文件。
- **repro 不一致**：确认未修改 `build_release.py` 的时间戳/权限逻辑，且 `.sha256` 与 zip 同时重建；`repro_check.py` 会先覆盖 `.sha256` 再比对两次构建。
- **文档链接误报**：`check_doc_links.py` 只认可仓库白名单目录（docs、packages、scripts、tests、content、config、contracts、tools、dist）与 `workbench.py` 入口开头的路径；运行时目录（`00_project/`）与 API 路径会被跳过。
- **远端 CI 未触发**：检查 `git remote -v`、分支保护与 workflow 触发条件；本地用 `run_ci.py` 复现。
