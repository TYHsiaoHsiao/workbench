# 迭代 0 交付报告（地基）

| 项 | 内容 |
|---|---|
| 版本 | workbench 0.1.0（契约 v1.0） |
| 日期 | 2026-11-14 |
| 范围 | 仓库骨架、contracts v1、stage-registry v1 + 校验、brand-guard v1 + 回归、CLI 骨架、CI |
| 结论 | **通过**：本地 CI 全绿；DoD 逐条满足；可进入迭代 1 |

## 1. 完成度（DoD）

| DoD | 结果 | 证据 |
|---|---|---|
| workbench 仓库骨架可运行 | 通过 | `python workbench.py version` → `workbench 0.1.0 (contracts v1.0)` |
| 6 份契约 schema 落地并可校验 | 通过 | `packages/contracts/schemas/`；单测覆盖正反例 |
| 阶段注册表 01–08 通过结构与引用校验 | 通过 | `python workbench.py check` → 校验通过 |
| 品牌守卫可运行且仓库零命中 | 通过 | `python workbench.py brand-guard` → 扫描 138 文件、命中 0 |
| 品牌守卫回归用例覆盖文本/Office/白名单 | 通过 | `tests/test_brand_guard.py` 11 项用例 |
| CLI 六个命令可用、退出码稳定 | 通过 | `version/doctor/check/brand-guard/init/validate`；退出码 0/1/2/3 |
| 本地 CI 一键运行 | 通过 | `python scripts/run_ci.py` → compile/tests/doctor/brand-guard 全 PASS（退出码 0） |
| GitHub Actions 模板就绪 | 通过 | `.github/workflows/ci.yml`：ubuntu/windows/macos × Python 3.11/3.12 |

## 2. 交付清单

- **契约**（6）：`state`、`reference-memory`、`knowledge-card`、`style-profile`、`stage-artifact`、`stage-registry`。
- **注册表**：`content/stage-registry.json`，8 阶段 + 知识桥元数据（`is_stage: false`、`default: off`）。
- **代码包**：`contracts`（子集校验器）、`core_router`（注册表/状态）、`brand_guard`（扫描/归一化/白名单）、`cli`（6 命令）、三个服务占位（knowledge/style/installer）。
- **配置**：`config/brand-guard.json`（8 个扫描目标、跳过规则、`safe_tokens`、20MB 上限）、`config/brand-allowlist.json`（第三方语料例外）。
- **测试**：42 项（契约 8、注册表 9、品牌守卫 12、CLI 7、init 6）。
- **脚本**：`scripts/run_ci.py`、`scripts/build_manifest.py`、`scripts/workbench.ps1`、`scripts/workbench.command`。
- **文档**：`README.md`、`docs/architecture.md`、`docs/brand-guard.md`、本报告。
- **发行清单**：`manifest.json`（38 个文件，含 SHA-256）。
- **CI**：`.github/workflows/ci.yml`（矩阵 6 任务）。

## 3. 验证证据

```text
$ python scripts/run_ci.py
=== compile: PASS ===
=== tests: PASS ===        # Ran 42 tests ... OK
=== doctor: PASS ===       # 5 项检查全 OK
=== brand-guard: PASS ===  # 扫描 138 个文件；命中 0 处
CI 全部通过               # 退出码 0
```

- `doctor` 检查：Python 3.12（≥3.10）、仓库骨架、6 份 schema 可加载、注册表 01–08 合法、词表可解码（2 项）。
- `init` 冒烟：临时目录创建项目，目录骨架 12 项、`state.json` 通过契约校验、生成文件零禁用词。

## 4. 关键设计与偏差处理

1. **契约先行、零第三方依赖**：校验器为标准库子集实现，避免给用户环境引入安装负担；错误格式统一 `$.path: message`。
2. **知识桥结构化为「非阶段」**：注册表用 `is_stage: false` + `default: off` 固化，防止未来演进中变成第 09 阶段。
3. **品牌守卫不落明文**：词表 base64 存储；报告只输出 `term#N`；归一化覆盖大小写、全半角、空格/分隔符插入。
4. **偏差：外部格式名误报**。守卫首跑命中 `aistudio-md-2`（知识库元数据中的外部 schema 名称，属于被引用事实，不是品牌文案）。处理：配置 `safe_tokens` 白名单机制，仅允许中性技术标识符；文档写明新增条件。
5. **偏差：报告残留旧路径名**。分析报告 P0 建议中出现含品牌片段的用户级配置路径，已改为 `~/.ai-film-workbench/knowledge-base.json`。
6. **偏差：用户文档目录不在 C 盘**。探测到 `C:\Users\<用户>\Documents` 不存在（实际在 D 盘）。`init` 默认改为仓库同级 `projects/<名称>/`，不硬编码盘符，跨平台安全。

## 5. 遗留与下一步

| 项 | 说明 | 归属 |
|---|---|---|
| M1 知识服务 | 只读适配现有知识库索引（`aistudio-md-2`），产出 knowledge-card 契约，不修改知识库 | 迭代 1 |
| M1 证据链校验 | 无本地路径/页码/命中词不得声称命中 | 迭代 1 |
| M2 风格服务 | 200 导演色卡 → style-profile → 多模型适配器 | 迭代 2 |
| M3 安装器 | 单一发行包安装/升级/回滚，含 L2 命令层中性化 | 迭代 3 |
| L3 目录级改名 | 需迁移脚本 + 回滚，默认后置 | 迭代 3+ |
| GitHub Actions 首次真实运行 | 模板已就绪，需推送远端后确认矩阵全绿 | 迭代 0 后续 |

## 6. 验收结论

迭代 0 的六项范围全部落地并通过本地 CI；关键架构约束（单阶段、确认点、知识桥非阶段、品牌中性）已由结构而非文档保证。**同意冻结 0.1.0，进入迭代 1（知识服务 PoC）。**
