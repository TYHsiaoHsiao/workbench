# 发行说明 · workbench 2.5.0（M17：PRD 验收对齐）

日期：2026-11-15
上一版：2.4.0（M16 队列失败重试、通知外送与守护日志）

## 能力

- **打包冒烟（PRD §11.3-4 / §11.4）**：`scripts/package_smoke.py` 校验 `.sha256`，解压到临时目录后执行 `version`、`doctor` 与 manifest 一致性检查；发行后必须通过，避免「CI 通过但交付物不可用」。
- **文档链接检查（PRD §11.3-5）**：`scripts/check_doc_links.py` 扫描 README/CHANGELOG/docs 的 Markdown 链接与行内代码仓库路径；跳过 URL、运行时目录（`00_project/` 等）与 `/api/...` 路径，已纳入 `run_ci.py`。
- **CLI 冷启动 NFR 基准（PRD §7）**：`scripts/bench.py` 统计 5 次 `version`/`doctor` 的中位数；`--enforce` 时冷启动超过 1.0s 返回非零，已纳入 CI。本机实测冷启动中位数约 254ms。
- **PRD 一致性修订**：文档版本号与变更记录对齐、修复悬空引用与变更表排序；§2.5 增加工作台能力指标；§11.1 增加 E2E-11/12；§11.2 契约数量更新；§11.3 补齐门禁；§9.22 记录本次迭代。
- **文档修复**：README 迭代表 M15/M16 行错乱修复；补发布与 CI 校验命令。

## 验证

| 项 | 结果 |
|---|---|
| 全量测试 | `Ran 368 tests ... OK`（新增 `tests/test_ci_scripts.py` 9 项） |
| 文档链接 | `scripts/check_doc_links.py`：247 处引用全部存在 |
| 冷启动基准 | 中位数约 254ms（≤1.0s 阈值） |
| 打包冒烟 | `dist/workbench-2.5.0.zip` 通过 SHA256/version/doctor/manifest |
| CI | compile / doc-links / tests / doctor / bench / brand-guard 全 PASS |
| 品牌守卫 | 0 命中 |

## 使用与升级

```bash
python scripts/run_ci.py          # 本地 CI（含文档链接与基准）
python scripts/build_manifest.py  # 发行清单
python scripts/build_release.py   # 发行包 + SHA256
python scripts/package_smoke.py   # 发行包冒烟（发行后执行）
```

升级方式：解压 `dist/workbench-2.5.0.zip` 覆盖旧目录即可；项目数据（`00_project/`）与外部知识库/风格包不受影响。

## 限制

- 文档链接检查只覆盖仓库内文档（README/CHANGELOG/docs）；不校验外部工作区文件。
- 冷启动基准依赖本机 Python 启动开销，不同机器数值有差异；阈值仅用于回归提示。
- 打包冒烟不覆盖安装器对 10 Skills 的外部安装（发行包不含 Skills 源包，见 PRD 风险 R6）。
- rollback 命令（PRD §11.4）仍未实现，列入后续迭代。
