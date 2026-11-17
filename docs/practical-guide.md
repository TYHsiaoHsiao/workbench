# 实操指南：10 分钟从零到第一条可提交提示词

> 版本：2.25.0（M38）· 适用范围：本地单用户（Web 仅监听 127.0.0.1）
>
> 目标：建项目 → 自检 → Web 预演 → 逐阶段产出 → 生成平台 dry-run / 真实提交（可选）。

## 0. 环境确认

```powershell
python workbench.py version
python workbench.py doctor          # 9-10 项自检，应全部 [OK]
```

要求：Python ≥ 3.10；仓库根目录执行；`AI_FILM_PROJECTS_ROOT` 可选（统一项目根）。

## 1. 一键准备实操项目（M38）

```powershell
python workbench.py quickstart 我的短片 --project-root "D:/AI影视工作台/projects"
```

- 自动创建项目骨架（`00_project/state.json` 等）并生成默认流程图 `flow-main`（从 01 到 08）
- 输出「下一步命令」清单：自检 → 启动 Web → 校验/预演 → 生成平台

非交互、可重复执行：同名项目会自动复用（不会覆盖）。

## 2. 实操自检

```powershell
python workbench.py practical-check --project "我的短片"
```

| 检查项 | 说明 |
|---|---|
| project | 项目状态可读、阶段正常 |
| registry | 8 阶段注册表可加载 |
| flow | 至少一张流程图，首图校验通过 |
| knowledge | 外部知识库可发现（可选能力） |
| index | 本地索引是否已构建（可选） |
| style | 200 位导演风格库可加载 |
| generate | 生成平台 provider 与 key 配置状态 |
| web | Web 面板启动命令 |

结论：无 `[FAIL]` 即可开始实操；`[WARN]` 按建议处理（如未配置真实平台 key 属正常）。

## 3. 打开 Web 面板

```powershell
python workbench.py flow serve --project "我的短片" --port 8899
```

访问终端打印的 `http://127.0.0.1:8899/?token=...`。

- 顶栏「实操指引」按钮：内置步骤速查
- 左侧节点库拖拽 / 连线；右侧检查器
- 右侧「运行」面板：勾选「预演（dry-run）」→ 运行，查看运行历史

## 4. 逐阶段产出（01 → 08）

按阶段推进即可，每阶段产物写入 `<阶段目录>/`，状态记录在 `00_project/state.json`：

```powershell
python workbench.py next --project "我的短片"      # 满足门禁后推进阶段
python workbench.py gate list --project "我的短片"
```

知识/风格辅助（可选）：

```powershell
python workbench.py knowledge search --project "我的短片" --stage 01 --problem "确定短片类型" --queries "悬念,节奏" --json
python workbench.py style list --json
python workbench.py style apply --project "我的短片" --style 002 --stage 08
```

## 5. 生成平台：先 dry-run，再 live

```powershell
python workbench.py generate providers            # 查看 provider 与 key 状态
python workbench.py generate plan mock --project "我的短片" --prompt-file 05_shots/shot-01-prompt.md --json
python workbench.py generate submit mock --project "我的短片" --prompt-file 05_shots/shot-01-prompt.md --json
```

真实平台（示例，需先设置环境变量）：

```powershell
$env:SEEDANCE_API_KEY = "<你的 key>"
python workbench.py generate submit seedance_2_5 --project "我的短片" --prompt-file 05_shots/shot-01-prompt.md --live
python workbench.py generate refresh --project "我的短片" --all
python workbench.py generate adopt <job_id> --project "我的短片" --stage 05
```

## 6. 记录、对比与回滚

```powershell
python workbench.py flow runs --project "我的短片"
python workbench.py flow batch --project "我的短片" --all --dry-run
python workbench.py flow batch-report --project "我的短片" --format html
python workbench.py rollback create --project "我的短片" --label "实操前"
python workbench.py rollback list --project "我的短片"
```

## 7. 常见问题

| 现象 | 处理 |
|---|---|
| quickstart 报项目已存在 | 默认复用；如需重来加 `--force` |
| practical-check 报 flow FAIL | 打开 Web 修复连线后 `flow validate` |
| 生成平台 key 未配置 | 先用 mock 跑通；live 前设置环境变量 |
| Web 打开是空画布 | 确认项目/流程图下拉选对；`flow new --template tpl-full-flow` |
| 端口被占用 | `flow serve --port 8900` 更换端口 |

更多：`docs/command-card.md`、`docs/troubleshooting.md`、`docs/ci.md`。
