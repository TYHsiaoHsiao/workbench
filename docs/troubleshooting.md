# 故障排查（v1.0）

> 先跑 `python workbench.py doctor` 与 `python workbench.py check`，多数问题能直接定位。
> 环境：Windows / macOS / Linux，Python >= 3.10；无第三方依赖。

## 1. `python` 命令不存在或版本过低

- 症状：`python: command not found` / `Python 3.9.x`。
- 处理：安装 Python 3.10+；Windows 可用 `py -3.12` 代替 `python`；确认 `python --version`。
- 工作台脚本自身会在 Python < 3.10 时报环境错误（退出码 3）。

## 2. `doctor` 报缺文件或契约加载失败

| 失败项 | 含义 | 处理 |
|---|---|---|
| `layout` | 仓库目录不完整 | 重新获取完整 `workbench/`；不要只拷贝 `workbench.py` |
| `contracts` | `packages/contracts/schemas/` 缺失或 JSON 坏 | 恢复 7 份 schema；跑 `check` 看具体错误 |
| `registry` | 阶段注册表校验失败 | 检查 `content/stage-registry.json` 是否被手改 |
| `intent-rules` | 意图规则缺失/坏 | 恢复 `content/intent-rules.json` |
| `style-registry` | 风格注册表缺失/坏 | 用 `python scripts/build_style_registry.py` 重建 |
| `brand-wordlist` | 词表无法解码 | 恢复 `packages/brand_guard/wordlist.b64` |

## 3. 项目找不到 / `init` 拒绝覆盖

- 症状：`未找到项目: xxx`。
- 处理：`--project` 可传**项目名**（自动到默认项目根找）或**绝对/相对路径**；默认根查看 `python workbench.py doctor` 或代码 `default_projects_root()`（默认「文档目录/AI 影视工作台/projects」）。
- 环境变量：`AI_FILM_PROJECTS_ROOT` 覆盖项目根；`AI_FILM_WORKBENCH_HOME` 覆盖工作台配置目录。
- `init` 对已存在目录默认拒绝，加 `--force` 才会覆盖。

## 4. 门禁未通过，`next` 被拒绝（退出码 1）

- 症状：`门禁未通过: shot_plan_gate(pending)`。
- 处理：`gate list --project 项目名` 查看当前阶段门禁；确认后 `gate pass <id>`。硬门禁（`hard`）不可豁免、不可跳过；`advance` 不会越过待处理门禁。
- 注意：`gate pass`/`style.*`/`reference` 等命令会读写 `00_project/state.json`；**不要同时手动编辑 state.json 再调用服务命令**，否则旧状态可能覆盖新门禁。脚本调用时先 `save_state`，再调用其它会写状态的命令。

## 5. 风格注入失败

| 提示 | 原因 | 处理 |
|---|---|---|
| `尚未应用风格卡` | 未 `style apply` | 先 `style apply <编号> --project 项目名` |
| `未通过结构校验：缺少必需标记: --ar` | mj 等工具要求标记缺失 | 提示词加 `--ar 9:16`（竖屏）等 |
| `运镜种类超限` | 08 一镜多运镜 | 正文只写一个运镜；风格卡前缀不参与该校验 |
| `阶段 0x 不支持风格注入` | 只在 06/08 挂载 | 06 用图像工具（mj/banana/sd），08 用视频工具（seedance_2_0/2_5/h3/runway/pika） |
| `命中多个条目` | 名称/目录部分匹配 | 改用 3 位编号，如 `001` |

## 6. 知识检索返回 `no_evidence`

- 这是**正确行为**：本地没有可验证命中时不得虚构参考。
- 处理：换关键词/换 lane（`screenplay:` / `method_book:` / `cultural_fact:`）；确认知识库已配置（`knowledge probe`）；必要时调大 `--fallback-files` / `--fallback-bytes`。
- 真实命中必须同时有本地路径、行号、命中词；缺少任一项时知识卡不会写 `ok`。

## 7. 中文输出乱码或 `UnicodeEncodeError`

- Windows PowerShell 5.1 下 `>` 重定向默认 UTF-16，读取日志要用 `encoding="utf-16"`；写文件建议 UTF-8。
- 提示词文件用 PowerShell `Set-Content -Encoding utf8` 会带 BOM；CLI 已用 `utf-8-sig` 读取容忍。
- 终端显示乱码时：`chcp 65001`，或设置 `PYTHONIOENCODING=utf-8`。

## 8. `brand-guard` 命中

- `term#N` 为脱敏编号，表示命中词表（不打印明文）。
- 报告字段：`path`、`line`、`term`；`skipped` 为跳过文件数，`missing_targets` 为配置中不存在的目标。
- 处理：把品牌字样改为中性描述；确属第三方语料内容时加入 `config/brand-allowlist.json`（目录级例外）。
- CI 中命中即失败（退出码 1）。

## 9. 迁移/升级失败

| 提示 | 处理 |
|---|---|
| `不是工作台项目（缺少 00_project/）` | 确认指向旧项目根目录 |
| `缺少 00_project/state.json：请先运行 migrate` | 先 `migrate --project <旧项目>`，再 `upgrade` |
| 迁移后内容异常 | `00_project/history/migrate-*` 下有迁移前备份，可按文件恢复；`migration-report.md` 记录字段映射 |
| 升级后规则不对 | `00_project/history/upgrade-*` 下有升级前备份；`upgrade-report.md` 记录变更 |

## 10. 导出/还原失败

| 提示 | 处理 |
|---|---|
| `目标项目目录非空，未覆盖` | 换空目录，或先手动清理（工作台不覆盖已有项目） |
| `导出包含非法路径` | 归档被篡改或非本工具生成；使用可信归档 |
| 还原后 stage 不一致 | 用 `check --project` 校验 state；`export-metadata.json` 内有导出时版本/阶段 |

## 11. `check --content` 与批量注入报错（1.0.1）

| 提示 | 含义与处理 |
|---|---|
| `风格卡文件不存在: …` | `state.style.status=on` 但卡片被删；重跑 `style apply <编号> --project <项目>` |
| `知识卡文件不存在: …` | `knowledge_bridge.status` 为 requested/on 但 `last_card` 不存在；重跑 `knowledge search --out` 或把状态改回 `off` |
| `confirmed_references 中的 参考方法0xx 不在 state.references` | 先通过采用流程写入参考记忆，再更新知识桥；不要手改 state.json |
| `stage_artifacts 引用的文件不存在: …` | 产物被移动/删除；重新 `artifact register` 最新路径 |
| `时长不一致: 场次 1-0X treatment=Ns，shot-plan=Ms` | treatment 预算与镜头规划不一致；改 shot-plan 的「场次时长预算」或在汇报中说明并统一 |
| `批量注入结构校验未通过：SH-xx: …` | 该条提示词缺必填结构（如 seedance_2_5 需要【整体】【光影】【镜头】【声音】【对白】）；修正后整批重跑，工作台不会写入半批 |
| `stage_artifacts 引用的文件不存在` 与 `--note` | 登记命令支持多 `--path`；同路径重复不会重复计数 |

说明：`check --content` 有错误时退出码 1，仅提示（warnings）时退出码 0；CI 不强制内容检查，需在阶段收尾时手动跑一次。

## 12. CI 与 PowerShell 退出码

- PowerShell 把 Python stderr 包装成 `NativeCommandError` 时，`$LASTEXITCODE` 可能不可靠；以 `scripts/run_ci.py` 输出中的 PASS/FAILED 与最终 `CI_EXIT` 为准。
- 本地推荐：`python scripts/run_ci.py`（内部逐项检查，失败即非零）。

## 13. 快速恢复

```text
1) python workbench.py doctor
2) python workbench.py check --project <项目>
3) python workbench.py gate list --project <项目>
4) 旧项目：python workbench.py migrate / upgrade（先看 reports）
5) Skill 安装：python workbench.py install --dry-run 预演
6) 仍失败：保留 00_project/history 下备份与终端输出，按报告路径排查
```
