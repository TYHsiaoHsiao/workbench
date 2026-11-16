# 命令卡（v2.24.0）

> 所有命令在 `workbench/` 目录下执行：`python workbench.py <命令>`。
> Python >= 3.10，无第三方运行时依赖。退出码：`0` 成功，`1` 校验失败/门禁拦截，`2` 参数错误，`3` 环境不可用。

## 1. 环境与自检

| 命令 | 作用 |
|---|---|
| `python workbench.py version` | 版本号 + 契约版本 |
| `python workbench.py doctor` | 10 项自检：Python、目录骨架、17 份契约、阶段注册表、意图规则、风格注册表、flow（17 节点/4 模板/6 契约）、generate（4 provider）、index（knowledge-index/knowledge-search 契约 + FTS5 trigram 可用）、品牌词表 |
| `python workbench.py check` | 校验阶段注册表；`--project <名或路径>` 同时校验项目 `state.json` 与参考记忆 |
| `python workbench.py check --project 项目名 --content` | 跨阶段内容一致性：风格卡/知识卡/产物文件存在性、`confirmed_references` 子集、treatment↔shot-plan 时长、下游过期提示（1.0.1） |
| `python workbench.py brand-guard` | 品牌禁用词扫描；`--json` 输出结构化报告 |
| `python scripts/run_ci.py` | 本地 CI：编译 → 文档链接 → FR 映射 → 测试 → 覆盖率≥80%/分支≥50% → doctor → 冷启动基准 → brand-guard → 可复现构建 |

## 2. 项目生命周期

| 命令 | 作用 |
|---|---|
| `python workbench.py init 项目名 --entry A` | 创建项目骨架（12 个目录 + `00_project/state.json` + 参考记忆 JSON/MD + 状态卡） |
| `python workbench.py project list`（加 `--stats` 输出流程/运行/待门禁/产物统计，1.4.0） |
| `python workbench.py project summary --project 项目名 [--json]` | 项目摘要：已登记产物文件、流程图节点/边、运行数（1.5.0） | 跨项目总览：扫描默认项目根与仓库同级 `projects/`（可多次 `--root`），显示阶段/版本/入口/风格/知识桥/更新时间（1.0.2） |
| `python workbench.py project snapshot --project <名称> [--label 标签]` | 产物快照（记录路径/sha256/大小） |
| `python workbench.py project snapshots --project <名称> [--json]` | 列出产物快照 |
| `python workbench.py project artifacts-diff --project <名称> [--base ID --target ID]` | 产物快照差异（默认最近快照 vs 当前） |
| `python workbench.py init 项目名 --entry B --force` | 覆盖已存在项目（默认拒绝覆盖） |
| `python workbench.py route "只做CINEDANCE"` | 意图路由：维护口令 > 知识库请求 > 直接入口 > 修订 > 阶段 > 入口 |
| `python workbench.py gate list --project 项目名` | 查看当前阶段门禁状态 |
| `python workbench.py gate pass <门禁id> --project 项目名 --note 说明` | 通过门禁（硬门禁不可豁免） |
| `python workbench.py gate fail <门禁id> --project 项目名 --note 原因` | 标记门禁失败 |
| `python workbench.py next --project 项目名` | 推进阶段；门禁未通过时退出码 1 并列出原因 |
| `python workbench.py artifact register --project 项目名 --stage 01 --kind 大纲 --path 01_story/synopsis.md` | 登记阶段产物：SHA-256 + 字节数写入 `stage_artifacts`，追加修订日志并刷新状态卡（1.0.1，支持 glob / 多 `--path`） |
| `python workbench.py reference list --project 项目名 --stage 05` | 查看当前阶段自动加载的参考方法编号 |
| `python workbench.py export --project 项目名` | 导出项目 ZIP（含 `export-metadata.json`） |
| `python workbench.py restore 归档.zip --dest 目标目录` | 还原导出包（校验路径穿越、目标非空拒绝覆盖） |

## 3. 旧项目迁移与升级

| 命令 | 作用 |
|---|---|
| `python workbench.py migrate --project 旧项目路径` | 旧目录结构 → 工作台结构：合并状态、生成 `reference-memory.json`、备份到 `00_project/history/migrate-*` |
| `python workbench.py upgrade --project 旧项目路径` | 规则升级：备份后重写 AGENTS 与状态卡、补齐目录、保留创作文件（备份在 `00_project/history/upgrade-*`） |

## 4. Skill 安装

| 命令 | 作用 |
|---|---|
| `python workbench.py install --source ../skills --dry-run` | 预演安装（10 个 Skill 校验） |
| `python workbench.py install --source ../skills` | 安装/升级 Skill：旧目录移入 `skills-backup-*`、保留 `knowledge-base.json` 字节、失败自动回滚 |

## 5. 知识服务（B 挂载，默认关闭）

| 命令 | 作用 |
|---|---|
| `python workbench.py knowledge probe` | 只读探测知识库（schema、文档数、FTS 可用性、问题列表） |
| `python workbench.py knowledge search --project 项目名 --stage 05 --problem "问题" --query "screenplay:悬疑 反转"` | 检索 → 知识卡（`ok` / `no_evidence` / `no_candidates`） |
| `... --index index` | M22：改用本地索引生成证据卡（四字段证据、page=段落标题；索引缺失/无命中分别报错/`no_evidence`） |
| `... --fallback-files 200 --fallback-bytes 262144` | 调整有限正文回退预算 |
| `... --no-fallback` | 关闭正文回退，只用元数据候选 |
| `... --out 项目/00_project/knowledge-cards/05-candidates.json` | 保存知识卡（默认只打印） |
| `python workbench.py knowledge bridge --project 项目名 --status requested --card 00_project/knowledge-cards/01-candidates.json` | 记录知识桥状态（off/requested/on）与确认编号（1.0.1，不触发检索） |

## 6. 风格服务（C 挂载，默认不注入）

| 命令 | 作用 |
|---|---|
| `python workbench.py style list --json` | 200 位导演；可按 `--category 01` / `--quality A` 筛选；文本模式显示分级数量与待核问题（1.0.2） |
| `python workbench.py style show 001` | 查看风格卡详情（调色板、光线、镜头、工具适配）；非 A 级会显示「质量提示」（1.0.2） |
| `python workbench.py style resolve 希区柯克` | 按编号/中英文名/目录解析 |
| `python workbench.py style validate 001 --tool mj --text "提示词正文"` | 结构校验（必填字段、禁用词、模型约束） |
| `python workbench.py style apply 001 --project 项目名` | 生成风格卡 `00_project/style-cards/style-001-profile.json` 并更新 `state.style` |
| `python workbench.py style inject 001 --project 项目名 --stage 06 --tool mj --prompt-file p06.txt` | 注入风格前缀 + 校验正文 + 写注入记录（阶段仅 06/08） |
| `python workbench.py style inject-batch --project 项目名 --batch batch.json [--out-dir 目录]` | 批量注入：整批校验、失败整批拒绝、写一份 `*-batch.json` 批量记录（1.0.1） |
| `python workbench.py style inject-batch ... --per-shot-records` | 额外写逐镜注入记录 `style-<id>-injection-<stage>-<tool>-<shot>.json`（1.0.2） |

## 7. 可视化节点工作流（flow）

| 命令 | 作用 |
|---|---|
| `python workbench.py flow serve --project 项目名 [--port 8899]` | 启动本机可视化工作台（打印带 token 的 URL；页面每 1.2s 轮询 `/api/dev/version` 实现实时预览；`--no-token` 仅本机调试） |
| `python workbench.py flow templates [--json]` | 模板库（4 套：从零到成片 / 入口接力 / 知识增强 / 风格注入） |
| `python workbench.py flow new --project 项目名 [--template tpl-full-flow] [--graph 流程id] [--force]` | 新建流程图（默认骨架或模板实例化） |
| `python workbench.py flow list / show / validate --project 项目名 [--graph 流程id]` | 流程列表 / 详情 / 校验（契约 + 语义 8 条） |
| `python workbench.py flow run --project 项目名 --graph 流程id [--dry-run/--live] [--mode full/to_node/single] [--node 节点id] [--yes]` | 运行（默认按图设置，建议先 dry-run；`--yes` 自动确认断点） |
| `python workbench.py flow run --project 我的短片 --graph flow-main --live --retries 2` | 真实运行并允许节点失败自动重试（`--retries 0–3`，默认 0；写状态节点重试可能重复副作用） |
| `python workbench.py flow runs --project 项目名 [--limit 20]` | 运行历史（状态/步骤/失败/恢复来源） |
| `python workbench.py flow recover --run run-id --project 项目名 [--restore-state] [--yes]` | 失败运行恢复（可选回滚 `state_snapshot_before` 快照后重跑） |
| `python workbench.py flow replay --run run-id --project 项目名 [--json]` | 运行回放（每步耗时、最慢节点、失败定位） |
| `python workbench.py flow diff --project 项目名 --run run-id [--other-run run-id] [--json]` | 两次运行对比（节点状态/耗时/回归/改善，1.5.0） |
| `python workbench.py flow baseline set --project <名称> --run <run_id> [--graph <流程id>]` | 保存运行基线 |
| `python workbench.py flow baseline show|clear --project <名称> [--graph <流程id>]` | 查看/清除运行基线 |
| `python workbench.py flow export --project 项目名 --graph 流程id --out flow.json` | 导出流程图 JSON（也可 `--file flow.json` 原样输出） |
| `python workbench.py flow import --project 项目名 --file flow.json [--graph 新id] [--force]` | 导入流程图（先校验，非法不落盘） |
| `python workbench.py flow batch --project 项目名 --all [--dry-run/--live] [--yes] [--auto-retry N] [--fail-fast] [--parallel] [--workers N] [--limit N]` | 批量运行项目内全部流程图（批次记录；失败图可自动重试 0–3 次；`--parallel` 仅 dry-run，线程数 1–8；JSON 输出为 `{ok,project,batch}`） |
| `python workbench.py flow batches --project 项目名 [--limit 20] [--json]` | 批次历史（最近批次摘要） |
| `python workbench.py flow batch-show --project 项目名 --batch batch-id [--json]` | 批次详情（每图状态/尝试/耗时/错误） |
| `python workbench.py flow batch-recover --project 项目名 --batch batch-id [--dry-run/--live] [--auto-retry N] [--parallel] [--workers N] [--json]` | 重跑批次中的失败图并把新尝试合并进原批次 |
| `python workbench.py flow batch --project 项目名 --all --webhook-url <URL>` | M28：批次有失败图时把 `event=batch.run` 汇总 JSON POST 到 webhook（失败不阻断批次，结果见 `webhook`） |
| `python workbench.py flow queue add --project 项目名 [--graphs a,b / --all] [--dry-run/--live] [--auto-retry N] [--fail-fast] [--parallel] [--workers N] [--at 2026-11-15T20:00] [--json]` | 把批量运行请求加入项目队列（`00_project/workflows/queue.json`；`--at` 定时到点执行） |
| `python workbench.py flow queue list --project 项目名 [--status pending/succeeded/failed/canceled] [--limit 50] [--json]` | 查看队列条目（状态/顺序/计划时间/图数/批次/失败通知） |
| `python workbench.py flow queue run --project 项目名 [--limit 5] [--retry-failed N] [--notify-cmd "命令"] [--json]` 或 `--all-projects` | 顺序执行 pending 条目，逐条生成批次并写回结果/失败通知；`--retry-failed` 先重置未达上限的失败条目，`--notify-cmd` 外送失败通知 |
| `python workbench.py flow queue cancel <queue_id> --project 项目名 [--json]` | 取消待运行（pending）队列条目 |
| `python workbench.py flow queue move <queue_id> --project 项目名 (--before ID / --after ID / --index N) [--json]` | 调整 pending 条目执行顺序（`order` 重赋 0..n-1） |
| `python workbench.py flow queue daemon --project 项目名 [--interval 30 | --cron "*/5 * * * *"] [--limit 5] [--until-empty] [--all-projects] [--retry-failed N] [--notify-cmd "命令"] [--webhook-url URL] [--log-file 路径] [--rotate-bytes N]` | 后台守护：周期执行到期条目，可自动重试/外送失败通知并写轮转日志（Ctrl+C 停止） |
| `python workbench.py flow queue retry <queue_id> --project 项目名 [--json]` | 重置失败条目为待运行（`attempts` +1，下次 run/daemon 再执行） |
| `python workbench.py flow queue notifications --project 项目名 [--limit 20] [--json]` | 查看失败通知外送日志（JSONL，最近在前） |

## 7.5 生成平台（generate，M8/M9/M10/M11）

| 命令 | 作用 |
|---|---|
| `python workbench.py generate providers [--json]` | 列出 4 个 provider 与 env key 设置状态（mock/seedance_2_0/seedance_2_5/minimax_h3） |
| `python workbench.py generate plan --provider seedance_2_5 --prompt-file 05_shots/shot-01-prompt.md [--shot 1-01] [--model m] [--json]` | 提交前预检：模型白名单、字数上限、sha256、时长估算、是否 dry-run |
| `python workbench.py generate submit --provider minimax_h3 --prompt-file ... [--live] [--project 项目名]` | 创建生成任务（默认 dry-run 只记录；`--live` 且 key 存在才真实提交） |
| `python workbench.py generate jobs --project 项目名 [--limit 20] [--json]` | 生成任务列表（created_at 倒序） |
| `python workbench.py generate show <job_id> --project 项目名 [--json]` | 任务详情（状态/请求/错误） |
| `python workbench.py generate refresh <job_id> --project 项目名 [--json]` | 查询平台任务状态并更新本地记录（仅 submitted 且非 dry-run） |
| `python workbench.py generate refresh --all --project 项目名 [--limit 20] [--json]` | 批量刷新 submitted 任务（单任务失败容错） |
| `python workbench.py generate retry <job_id> --project 项目名 [--live/--dry-run] [--json]` | 重试 failed/canceled 任务（默认沿用原提交方式，新任务记录 `retried_from`） |
| `python workbench.py generate adopt <job_id> --project 项目名 [--stage 05] [--kind generation] [--note 备注] [--json]` | 回填 succeeded 结果：写结果凭证并登记 `state.stage_artifacts` |
| `python workbench.py generate adopt --all --project 项目名 [--limit 20] [--stage 05] [--json]` | 批量回填全部 succeeded 且未回填任务（组合登记 state 产物摘要） |

## 8. 契约校验

| 命令 | 作用 |
|---|---|
| `python workbench.py validate 文件.json --schema state.schema.json` | 按契约校验任意 JSON |

## 9. 典型工作流

```bash
# 从零到 08
python workbench.py init 雨夜回声 --entry A
python workbench.py gate pass positioning_menu --project 雨夜回声
python workbench.py next --project 雨夜回声
...
python workbench.py export --project 雨夜回声

# 既有剧本接力（B 入口）
python workbench.py init 旧剧本接管 --entry B
python workbench.py migrate --project 旧项目          # 仅旧目录项目需要
python workbench.py knowledge search --project 旧剧本接管 --stage 05 \
  --problem "接管检查与生产资料补齐" --query "method_book:三幕式结构 悬念"

# 风格注入（06/08）
python workbench.py style apply 001 --project 雨夜回声
python workbench.py style inject 001 --project 雨夜回声 --stage 06 --tool mj --prompt-file p06.txt

# 可视化节点工作流（先预演，再 live）
python workbench.py flow serve --project 雨夜回声
python workbench.py flow new --project 雨夜回声 --template tpl-full-flow --name 从零到成片
python workbench.py flow run --project 雨夜回声 --graph flow-main --dry-run
```

## 10. 发布与 CI 校验（M17）

| 命令 | 作用 |
|---|---|
| `python scripts/run_ci.py` | 本地 CI：编译 → 文档链接 → FR 映射 → 测试 → 覆盖率≥80%/分支≥50% → doctor → 冷启动基准 → 品牌守卫 → 可复现构建 |
| `python scripts/ci_ready.py [--require-remote] [--json]` | 远端 CI 就绪检查：工作流矩阵/步骤 + `git remote`（M26，8 项测试） |
| `python scripts/check_doc_links.py [--json]` | 文档链接检查：Markdown 链接与行内代码中的仓库内路径必须存在 |
| `python scripts/check_fr_mapping.py [--json]` | FR 追溯映射检查：FR-01–FR-22 全覆盖、无重复/非预期 ID，并与 PRD 头衔交叉校验（M19） |
| `python scripts/coverage_check.py [--min 80] [--json] [--out <文件>]` | 零依赖行覆盖率（`packages/`，跳过 docstring/import；2.11.0 实测 80.8%，CI `--min 80`） |
| `python scripts/coverage_check.py --branches --min-branches 50 [--json]` | 分支覆盖率（`dis` 静态分支点 + 局部 `sys.monitoring` BRANCH 事件；2.13.0 实测 50.52%，CI 门禁 50%） |
| `python scripts/repro_check.py [--json]` | 可复现构建：两次构建与 `.sha256` 三方一致（M20） |
| `python scripts/bench.py [--runs 5] [--max-cold-start 1.0] [--enforce] [--json]` | NFR 基准：CLI 冷启动/doctor 耗时中位数（`--enforce` 超阈值退出 1） |
| `python scripts/build_manifest.py` | 生成发行清单 `manifest.json`（文件级 SHA256） |
| `python scripts/build_release.py` | 生成发行包 `dist/workbench-<版本>.zip` 与 `.sha256` |
| `python scripts/package_smoke.py [--zip <路径>] [--json]` | 发行包冒烟：SHA256 → 解压到临时目录 → `version`/`doctor`/manifest 一致性 |
| `python scripts/rollback_drill.py [--json] [--dist <目录>]` | 发行包升级→回滚演练：安装上一版→升级最新→回滚上一版并校验版本 |

## 11. 项目快照与回滚（M18）

| 命令 | 作用 |
|---|---|
| `python workbench.py rollback create --project <项目> [--label 标签] [--json]` | 创建项目状态快照（`00_project/history/snapshots/`，含 state/参考记忆/状态卡/流程图 JSON） |
| `python workbench.py rollback list --project <项目> [--json]` | 快照列表（创建时间倒序） |
| `python workbench.py rollback apply --project <项目> --snapshot <snap_id> [--dry-run] [--json]` | 回滚到快照：回滚前自动创建安全快照；`--dry-run` 只显示计划 |

## 12. 跨平台 CI 与覆盖率（M20）

| 命令/文件 | 作用 |
|---|---|
| `.github/workflows/ci.yml` | GitHub Actions：ubuntu/windows × Python 3.11/3.12 + macOS × 3.11（共 5 作业；macOS 3.12 因 runner 排队不稳定暂排除）；M26 硬化 permissions/concurrency/timeout/UTF-8 并加 ci_ready 就绪步骤 → run_ci → build_release → package_smoke → 上传 artifact |
| `python scripts/coverage_check.py [--min 80] [--branches --min-branches 50] [--json]` | 行覆盖率 2.13.0 实测 80.84% + 分支覆盖率 50.52%（CI 门禁 80/50） |
| `python scripts/repro_check.py [--json]` | 可复现构建：两次构建与 `.sha256` 三方一致 |
| `docs/ci.md` | 门禁清单/矩阵/覆盖率策略/排障 |
| `docs/github-actions.md` | 远端 CI 接入指南（M26：remote/Actions、矩阵耗时、artifact、排障） |

## 13. 知识库索引维护（M21/M22/M24/M27/M29/M30）

| 命令 | 作用 |
|---|---|
| `python workbench.py index build --source <目录> [--out index] [--incremental] [--index-id ID] [--json]` | 按契约重建索引（默认全量；`--incremental` 复用未变文件、重索引变更、删除消失文档） |
| `python workbench.py index info [--out index] [--json]` | 索引信息（index_id/模式/来源/文档与分块数/更新时间） |
| `python workbench.py index verify [--out index] [--json]` | 校验元数据契约、库计数与 FTS 可查询性 |
| `python workbench.py index health [--out index] [--source 源目录] [--json]` | M29：健康巡检（元数据/文档/FTS 一致性、无主/空分块、重复路径、源目录陈旧度），问题退出码 1 |
| `python workbench.py index search --query <词> [--limit 8] [--mode hybrid] [--out index] [--json]` | 全文检索：`--mode auto|fts|like|hybrid`（默认 hybrid，标题/路径/短语/覆盖率加权）；≥3 字走 FTS5 trigram，短词 LIKE 回退（M24）；M30：`--min-score` 分数阈值、`--max-per-file` 每文件上限 |
| `python workbench.py index search --query <词> [--mode hybrid] [--config <path>] [--weights heading=3,path=1,phrase=2,coverage=1]` | M27：自定义检索权重与查询扩展（默认 `content/knowledge-search.json`；`--weights` 仅 hybrid 生效）；M29：配置可选 `synonym_weight`（0–1，默认 0.5）控制同义词在词项覆盖率中的权重 |
| `python workbench.py knowledge search --project 项目名 --stage 01 --problem "问题" --query "查询词" --index index` | M22：索引检索并生成同契约知识卡（`--json` 输出 report；不写参考记忆） |

## 14. 队列 webhook 通知（M24）

| 命令 | 作用 |
|---|---|
| `python workbench.py queue run --project <项目> [--limit 5] [--webhook-url <URL>]` | 执行队列；失败汇总 JSON POST 到 webhook（失败不阻断队列） |
| `python workbench.py queue daemon --project <项目> [--webhook-url <URL>] ...` | 守护模式下同样外送 webhook 失败汇总 |
| `python workbench.py flow batch --project <项目> --all --webhook-url <URL>` | M28：批次失败汇总 JSON POST（`event=batch.run`，含 `failed_graphs` 与 `summary`） |
| Web：运行面板「批次历史」 | M28：最近 10 个批次；失败行「恢复失败图」→ `POST /api/batches/<id>/recover` |

## 15. 队列运维与批次趋势（M31/M32/M33/M34/M35/M36/M37）

| 命令 | 作用 |
|---|---|
| `python workbench.py flow cron-preview --expression "*/5 * * * *" [--count 3] [--json]` | cron 表达式预览下一次触发时间（5 段：分 时 日 月 周；非法表达式退出 1） |
| `python workbench.py flow queue alerts --project <项目> [--limit 20] [--json]` | 失败通知聚合：条数/最近时间与消息/失败图 Top5/最近记录 |
| `python workbench.py flow queue alerts --project <项目> --webhook-url <url>` | 聚合失败通知并把摘要 POST 到 webhook（M32；`event=queue.alerts.digest`，失败时 EXIT_FAIL） |
| `python workbench.py flow queue alerts --project <项目> --fail-if-failures` | 存在失败通知时退出码 2（巡检/cron 判断，M32） |
| `python workbench.py flow queue alerts --project <项目> --webhook-format feishu --webhook-retries 2 --webhook-url <url>` | M33：飞书文本消息格式外送 + 失败固定退避重试（0–3，记录 `attempts`）；对 `queue run`/`queue daemon`/`flow batch` 同样可用 |
| `python workbench.py flow queue alerts --project <项目> --dedupe-minutes 30 --webhook-url <url>` | M34：相同告警静默窗口去重（默认 30 分钟，`0` 关闭）；窗口内不重复外送，返回 `suppressed=true` |
| Web：批次历史「报表 MD / 报表 CSV / 报表 HTML / 报表预览」 | M34/M35：`GET /api/batches/report?project=<项目>&limit=20&format=md\|csv\|html`（只读，复用 `flow batch-report` 汇总） |
| Web：批次历史「推送报表」 | M36：`POST /api/batches/report/push`（body project/webhook_url/limit/format/webhook_format/retries → `{ok,summary,webhook}`） |
| `python workbench.py flow batch-report --project <项目> [--format md|csv|html] [--out 路径] [--json]` | M33/M35：最近批次趋势报表（批次数/图数/成功/失败/成功率/平均耗时），可写文件或输出 JSON 摘要；html 为自包含单文件报告 |
| `python workbench.py flow batch-report --project <项目> --push --webhook-url <url> [--webhook-format generic|feishu] [--webhook-retries 0–3]` | M36：把批次报表摘要推送到 webhook（`event=batch.report`），失败按 retries 固定退避重试 |
| `--webhook-format feishu_card` | M37：飞书卡片消息（`msg_type=interactive`，告警红/报表绿），适用于 `batch-report --push`、`queue alerts`、`queue run`、`queue daemon`、`flow batch`。 |
| `python workbench.py flow batch-trend --project <项目> [--limit 10] [--out 路径] [--json]` | M37：导出批次趋势 SVG 图（自包含单文件，成功/失败条形）；`--out` 写文件，缺省打印到标准输出。 |
| Web：运行面板「批次历史趋势」/「失败告警」/「cron 预览」 | M31：`POST /api/cron/preview` + `GET /api/queue/alerts`；趋势为最近 10 批次成功/失败 SVG 条 |
