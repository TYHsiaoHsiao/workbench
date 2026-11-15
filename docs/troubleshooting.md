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
- 项目分散在多个根：`python workbench.py project list` 一次列出默认根与仓库同级 `projects/` 的全部项目（可多次 `--root` 追加其他根）；加 `--json` 便于脚本处理。

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

## 14. 可视化工作台（flow）常见问题

- `flow serve` 打不开：确认 127.0.0.1 端口未被占用（用 `--port` 换端口）；URL 必须带 token，`--no-token` 只用于本机临时使用。
- 图校验报「端口类型不兼容」：确认连接方向与端口类型（`artifact` 可连 `confirm` 与阶段，`state` 只进阶段/能力节点）。
- 运行停在 `awaiting_confirm`：人工确认节点未处理；在页面抽屉点确认，或重新运行验证。
- 运行失败想重跑：先 `flow runs --project <项目>` 查看记录，再 `flow recover --run <run_id> --project <项目> --yes`；需要回滚状态快照时加 `--restore-state`。
- 批量运行默认 dry-run，真实执行需显式 `--live`。
- 并行执行不生效：确认图 `settings.parallel=true`，且该波所有节点类型都带 `parallel_safe`；当前仅 `check_content`/`end` 可并行，其余写状态节点强制串行。
- 重试没有发生：节点 `retries` 与 `settings.node_retries` 默认均为 0；`flow run --retries N` 只覆盖默认值，节点显式 `retries` 优先。写状态节点重试前请确认幂等性。
- 条件/循环图校验报错：`condition` 必须恰好各一条 true/false 出边且不得在循环体内；`loop` 的 body 必须单链、非空、类型在白名单内，且不支持嵌套循环。
- `flow diff --baseline` 报「基线不存在」：先执行 `flow baseline set --project <项目> --run <run_id>`；回归阈值用 `--max-regressions` / `--max-delta-ms` 调整。
- 产物快照差异为空：快照只覆盖 01_story…06_prompts 下的文件，且需先执行 `project snapshot`；`?refresh=1` 只影响项目摘要缓存，不影响快照。
- 复合节点 `knowledge_adopt` 报「知识卡尚未确认」：先人工确认知识卡（`confirmed.by` 非空），或把节点参数 `require_confirmed=false`；重复证据会自动跳过。
- `style_bind` 提示「风格参考已存在」：同一风格画像已绑定过；如需重建先清理参考记忆中的 `style_reference` 条目。
- `generate` 节点/CLI 报「缺少环境变量 …API_KEY」：真实提交需要对应平台 key；默认 dry-run 不校验 key，`--live` 才需要。
- `generate submit` 超时或网络错误：任务会记为 failed 并保留错误文本；用 `generate show <job_id>` 查看，确认平台可达后重试。
- `generate refresh` 报「dry-run 记录，没有平台状态可查询」：只有真实提交（submitted）且非 dry-run 的任务能刷新；mock / dry-run 任务只是本地记录。
- 刷新报「缺少 …_BASE_URL / …_API_KEY 环境变量」：状态查询需要 provider 的 `base_url_env`（如 `SEEDANCE_BASE_URL`）与 API key；配置环境变量后重试。
- 刷新后任务仍是 submitted：平台可能仍在排队/生成中；稍后再点刷新或执行 `generate refresh --all`。批量刷新中单个任务失败会返回 `ok=false` 与错误文本，不影响其他任务。
- `generate retry` 报「只有 failed / canceled 任务可以重试」：重试只针对终态失败任务；排队/成功任务请用 `generate refresh` 或新提交。新任务记录 `retried_from` 指向原任务。
- `generate adopt` 报「只有 succeeded 任务可以回填结果」/「已回填过」：先 `generate refresh` 确认 succeeded 且未回填；回填默认写 `05_shots/generations/` 凭证并登记 `state.stage_artifacts`，重复回填会被拒绝。
- `generate_refresh` / `generate_adopt` 节点报「需要 job_id 或 all=true」：节点参数必须显式指定任务或批量开关，节点不会自动轮询/回填。
- `generate adopt --all` 没有回填任何任务：只处理 succeeded 且未回填的任务；先 `generate refresh --all` 刷新状态，并确认任务响应里有结果 URL。
- 回填报「没有可回填的结果 URL」：平台成功响应里未带 video_url/output_url 等结果字段；用 `generate show <job_id>` 检查 response 结构，必要时从平台手动获取结果后登记产物。
- `flow batch-show` 报「非法批次 ID」：`--batch` 需传批次列表中的 `batch-...` ID（不是 run_id）；先 `flow batches` 查看。
- 批次里某图始终失败：查看批次详情 `attempts`/`error`；`--auto-retry` 只重试失败图（每次新 run_id），图校验失败的尝试不会生成运行记录；修复图后重跑。
- 旧脚本解析 `flow batch --json` 报错：2.0.0 起输出由 `{count,results}` 改为 `{ok,project,batch}`，请改读 `batch.graphs`（Web 兼容别名 `/api/runs/batch` 仍返回旧字段）。
- 修改前端文件后页面不自动刷新：确认 `workbench version` ≥ 2.0.1，浏览器可访问 `/api/dev/version`；仅跟踪 3 个内置静态资源，后端 Python 改动需重启 `serve`。
- 「● 实时预览」不显示或轮询 401：URL 缺 token 或 token 失效，重新复制 `flow serve` 打印的带 token 地址。
- `flow batch --parallel` 报「并行批次仅支持 dry-run 预演」：live 运行共享项目状态，需去掉 `--parallel`（或改用 `--dry-run`）；`--parallel` 与 `--fail-fast` 也互斥。
- `flow batch-recover` 后仍失败：恢复只重跑原批次中失败图，修复图/参数后再次恢复；`flow batch-show` 可查看每次尝试的 `error`。
- `flow queue add` 报「没有可加入队列的流程图」：项目内还没有流程图，或 `--graphs` 传了不存在的 id；先 `flow list` 或 `flow new`。
- `flow queue run` 后条目仍 pending：单次 `--limit` 默认 5，剩余条目保持 pending，可再次执行或调大 `--limit`；`--all-projects` 只扫描默认项目根。
- 队列条目失败并显示「通知：批次 … 失败 N 个图」：用 `flow batch-show <batch_id>` 查看失败尝试，修复后重跑；队列不做自动重试。
- `flow queue add --at` 报「无法解析计划时间 …」：用 ISO 8601（如 `2026-11-15T20:00`），留空表示立即执行。
- 到点条目仍显示「计划中」未执行：`flow queue run` 不会自动等待，需启动 `flow queue daemon`（保持进程运行）或手动 run；`flow queue list` 可查看 `scheduled_at`。
- `flow queue cancel/move` 报错：只能操作 pending 条目，先 `flow queue list --status pending` 确认条目状态。
- `flow queue retry` 报「只能重试失败条目」：仅 failed 可重置，pending/running 无需重试；用 `flow queue list --status failed` 确认。
- `--retry-failed` 没有效果：仅重置 `attempts < N` 的失败条目；达到上限后不再重试，需手动 `flow queue retry` 或调大 N。
- `--notify-cmd` 未收到通知：命令按 `shlex` 拆分且消息作为最后一个参数传入，超时 10 秒；失败静默跳过，可用 `flow queue notifications` 查看 JSONL 日志确认通知是否已生成。



- 回放没有耗时/失败定位：先确认该运行记录含 `started_at` / `ended_at`（旧运行记录缺时间戳时回放只给步骤序列）；`flow replay --json` 可查看原始字段。
- 导入流程图报「流程图校验失败」：逐条对照图校验 8 条规则；导入前可先 `flow export` 再 `flow import` 自检；同 id 已存在需 `--force`。
- 导入后运行失败：导入只含流程图，项目状态仍以当前项目 `state.json` 为准；跨项目迁移请用 `export` / `restore`。
- 运行对比提示「没有可对比的另一次运行」：至少需要两条运行记录（可先 `flow run --dry-run` 两次，或显式传 `--other-run`）。
- 节点报「状态锁失败」：确认没有残留 `00_project/.locks/state.lock`（超过 120 秒会自动视为陈旧锁清理）；事务记录见 `00_project/history/transactions.jsonl`。
- 项目预览为空或 404：`project summary` 只读取已登记产物与 `00_project/workflows/` 下的流程图；先运行一次或 `flow new` 建图。

