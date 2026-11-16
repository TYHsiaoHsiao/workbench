# AI 影视工作台（workbench）

把一个「剧本到视频提示词」的创作流程，从一堆提示词与 Skill 文件，升级成可执行、可校验、可交接的工作台。

- **8 个创作阶段**（01 概念锚定 → 08 视频提示词）由路由表统一描述；
- **知识服务**与**风格服务**作为可选挂载点，默认关闭、按需启用；
- **契约先行**：阶段产物、参考记忆、知识卡、风格画像、项目状态全部有 JSON Schema；
- **品牌守卫**：仓库与工作区零品牌残留，CI 阻断回归。

当前版本 `2.24.0`：迭代 0（地基）、迭代 1a（B 知识服务 PoC）、迭代 2 方案 A（有限正文回退）、迭代 2.1（精度修订）、迭代 1b（A 编排硬化）、迭代 3（C 风格服务）、迭代 4（试点与固化）、1.0.1（真实项目补丁）、1.0.2（工作台体验补丁）、M1（可视化节点工作台骨架，1.1.0）、M2/M3（可视化节点工作台能力层，1.2.0）、M4（运行回放与图导入导出，1.3.0）与 M5（并行执行、节点级重试、项目管理面板，1.4.0）与 M6（状态锁与事务、运行对比、项目预览，1.5.0）以及 M7（条件分支与循环、运行基线与回归告警、产物快照差异，1.6.0）与 M8（复合节点与真实生成平台适配，1.7.0）以及 M9（生成任务状态轮询与 Web 生成面板，1.8.0）与 M10（生成结果回填、失败重试与任务详情抽屉，1.9.0）与 M11（批量回填、生成平台流程节点与生成面板筛选，1.10.0）与 M12（批次编排、批量自动重试与批次历史，2.0.0）已完成；2.0.1 为实时预览与界面迭代补丁（`/api/dev/version` 自动刷新、节点分类视觉与 17 类节点演示图，见 `docs/release-notes-2.0.1.md`）；2.1.0 为 M13 批次增强（批次并行预演（仅 dry-run）、失败图一键恢复与批次恢复 API，见 `docs/release-notes-2.1.0.md`）；2.2.0 为 M14 批次队列化与失败通知（项目内批次队列、顺序执行与失败汇总通知、CLI 跨项目 `--all-projects`，见 `docs/release-notes-2.2.0.md`）；2.3.0 为 M15 队列增强（定时调度、条目取消/重排与 `flow queue daemon` 后台守护，见 `docs/release-notes-2.3.0.md`）；2.4.0 为 M16 队列失败重试与通知外送（失败条目重试、JSONL 通知日志与 `--notify-cmd` 外送、daemon 日志轮转，见 `docs/release-notes-2.4.0.md`）；2.5.0 为 M17 PRD 验收对齐（打包冒烟、文档链接检查、CLI 冷启动基准、PRD 指标/验收章节一致性修订，见 `docs/release-notes-2.5.0.md`）；2.6.0 为 M18 项目状态快照与回滚（`rollback create/list/apply` 快照与安全回滚、`scripts/rollback_drill.py` 发行包升级→回滚演练，见 `docs/release-notes-2.6.0.md`）；2.7.0 为 M19 需求追溯与 FR↔里程碑映射（`docs/requirements-traceability.md`、`scripts/check_fr_mapping.py` 纳入 CI，见 `docs/release-notes-2.7.0.md`）；2.8.0 为 M20 跨平台 CI 矩阵、覆盖率与可复现构建门禁、Web 快照回滚面板（见 `docs/release-notes-2.8.0.md`）；2.9.0 为 M21 知识库索引维护（按契约重建/增量索引、SQLite FTS5 trigram 全文检索与 `workbench.py index` CLI，见 `docs/release-notes-2.9.0.md`）；2.10.0 为 M22 本地索引接入知识服务（`search_index_card` 用 `index/` 生成同契约知识卡、CLI `knowledge search --index`、flow `knowledge_search` 节点 `index` 参数，见 `docs/release-notes-2.10.0.md`）；2.11.0 为 M23 覆盖率提升与 80% CI 门禁（行覆盖率 80.8%、CLI 广覆盖与 Web 错误路径测试，见 `docs/release-notes-2.11.0.md`）；2.12.0 为 M24 索引混合排序与队列 webhook 通知（`index search --mode hybrid`、`queue run/daemon --webhook-url`，见 `docs/release-notes-2.12.0.md`）；2.13.0 为 M25 分支覆盖率门禁（行覆盖 ≥80% + 分支覆盖 ≥50%、`coverage_check.py --branches`，见 `docs/release-notes-2.13.0.md`）；2.13.1 为 M26 远端 CI 工作流硬化与就绪检查（concurrency/permissions/timeout、`scripts/ci_ready.py`、`docs/github-actions.md`，见 `docs/release-notes-2.13.1.md`）；2.14.0 为 M27 索引检索配置增强（权重/同义词/停用词与 hybrid 查询扩展，`index search --weights/--config`，见 `docs/release-notes-2.14.0.md`）；2.15.0 为 M28 队列运维增强（`flow queue daemon --cron` 定时守护、批次失败 webhook、Web 批次历史面板，见 `docs/release-notes-2.15.0.md`）；2.16.0 为 M29 索引健康巡检与同义词权重（`index health` 结构/FTS/陈旧度巡检、`synonym_weight` 词项加权，见 `docs/release-notes-2.16.0.md`）；2.17.0 为 M30 检索结果精细化（`min_score`/`max_per_file`/`snippet_chars`/`proximity_weight` 可配置、查询词邻近度加权，见 `docs/release-notes-2.17.0.md`）；2.18.0 为 M31 批次/队列运维收尾（cron 表达式预览、批次历史趋势图、队列失败告警聚合，见 `docs/release-notes-2.18.0.md`）；2.19.0 为 M32 队列告警运维闭环（`flow queue alerts --webhook-url` 告警摘要外送、`--fail-if-failures` 巡检退出码、Web 一键恢复全部失败批次，见 `docs/release-notes-2.19.0.md`）。2.20.0 为 M33 告警外送增强与批次趋势报表（webhook 重试/退避与飞书文本格式、`flow batch-report` Markdown/CSV 报表，见 `docs/release-notes-2.20.0.md`）；2.21.0 为 M34 批次报表 Web 化与告警静默窗口（Web `GET /api/batches/report` 与批次面板报表预览/导出 MD/CSV、`flow queue alerts --dedupe-minutes` 相同告警静默去重，见 `docs/release-notes-2.21.0.md`）；2.22.0 为 M35 批次报表 HTML 化（自包含 HTML 报告、CLI/Web `--format html`，见 `docs/release-notes-2.22.0.md`）；2.23.0 为 M36 批次报表推送与告警静默窗口状态（`flow batch-report --push`、Web 批次面板「推送报表」、告警面板显示静默窗口，见 `docs/release-notes-2.23.0.md`）。三个试点：从零到 08（`试点A-雨夜回声`）、既有剧本到 05（`试点B-旧剧本接管`）、真实项目从零到 done（《死亡外科医生》，见 `docs/pilot-c-report.md`），指标与证据见 `docs/pilots/`。 M37（飞书卡片通知与批次趋势 SVG 图，2.24.0）已完成（见 `docs/release-notes-2.24.0.md`）。
- `docs/release-notes-2.24.0.md`：2.24.0 发行说明（M37 飞书卡片消息 + 批次趋势 SVG 图）。

## 目录结构

```text
workbench/
  workbench.py               # CLI 入口
  VERSION                    # 版本号
  manifest.json              # 发行文件清单（scripts/build_manifest.py 生成）
  content/
    stage-registry.json      # 阶段注册表 v1：8 阶段 + 知识桥元数据
    intent-rules.json        # 意图路由规则（维护口令隔离 / 知识库 / 阶段 / 入口 / 修订）
    style-registry.json      # 风格注册表 v1：200 位导演色卡元数据 + 质量分级（只读引用外部风格包）
    flow-node-types.json     # 可视化节点类型注册表 v0.1：17 类节点、端口与参数 schema
  config/
    brand-guard.json         # 品牌守卫配置（目标、跳过、允许例外）
    brand-allowlist.json     # 允许例外清单（第三方语料）
  packages/
    contracts/               # JSON Schema + 子集校验器
    core_router/             # 注册表、状态构造、门禁引擎、意图路由、项目初始化、旧项目迁移
    brand_guard/             # 禁用词扫描与报告
    cli/                     # 命令行
    knowledge_service/       # 只读知识适配、元数据+有限正文回退、证据质量评分、行级证据链、知识卡
    style_service/           # 风格注册表解析、风格卡构建、8 工具适配、06/08 注入与记录
    installer/               # Skill 安装/升级：备份、幂等、回滚、配置保留
    flow/                    # 可视化节点工作流：图模型与校验、节点注册表、执行引擎、项目内存储
    webui/                   # 本地 Web 服务 + 原生前端（画布/拖拽/连线/检查器/运行面板）
    generate/                # 生成平台适配层：4 provider 登记、任务记录（job 契约）、dry-run 默认
  tests/                     # 524 个 unittest 用例
  scripts/                   # run_ci.py / build_manifest.py / pilot_matrix.py / 平台包装
  docs/                      # 架构、品牌守卫、命令卡、故障排查、迁移说明、迭代报告、pilots/
  .github/workflows/ci.yml   # GitHub Actions
```

## 快速开始

要求：Python >= 3.10，无第三方运行时依赖。

```bash
python workbench.py version          # 版本与契约版本
python workbench.py doctor           # 环境与仓库自检（失败退出码 3）
python workbench.py check            # 校验阶段注册表
python workbench.py brand-guard      # 扫描品牌禁用词（命中退出码 1）
python workbench.py init 我的短片 --entry A   # 创建项目骨架（状态卡 v2）
python workbench.py project list              # 跨项目总览（阶段/版本/风格/知识桥，扫描默认与仓库同级 projects/）
python workbench.py route "只做CINEDANCE"     # 意图路由（维护口令优先隔离）
python workbench.py gate list --project 我的短片        # 查看当前阶段门禁
python workbench.py gate pass positioning_menu --project 我的短片
python workbench.py next --project 我的短片             # 门禁未通过会被拒绝（退出码 1）
python workbench.py install --source ../skills --dry-run # 安装/升级 Skill（备份+回滚）
python workbench.py migrate --project 旧项目            # 旧项目迁移到状态卡 v2
python workbench.py upgrade --project 旧项目            # 旧项目规则升级（备份后更新）
python workbench.py knowledge probe           # 探测本地知识库（只读）
python workbench.py knowledge search --project 我的短片 --stage 05 \
  --problem "当前阶段的问题" --query "screenplay:悬疑 反转" \
  --fallback-files 200 --fallback-bytes 262144 \
  --out 我的短片/00_project/knowledge-cards/05-candidates.json
python workbench.py knowledge search --project 我的短片 --stage 01 \
  --problem "开场如何建立悬念" --query "建立悬念" --index index  # M22：用本地索引生成证据卡
python workbench.py style list --json                    # 风格注册表 200 条（可 --category 01 --quality A）
python workbench.py style apply 001 --project 我的短片   # 生成风格卡并更新 state.style
python workbench.py style inject 001 --project 我的短片 --stage 06 --tool mj --prompt-file p06.txt
python workbench.py style inject-batch --project 我的短片 --batch batch.json  # 批量注入，写一份批量记录
python workbench.py style inject-batch --project 我的短片 --batch batch.json --per-shot-records  # 再写逐镜注入记录
python workbench.py artifact register --project 我的短片 --stage 01 --kind 大纲 --path 01_story/synopsis.md
python workbench.py knowledge bridge --project 我的短片 --status requested --card 00_project/knowledge-cards/01-candidates.json
python workbench.py check --project 我的短片 --content        # 跨阶段内容一致性检查（风格卡/知识卡/产物/时长）
python workbench.py reference list --project 我的短片 --stage 05        # 当前阶段自动加载的参考方法
python workbench.py export --project 我的短片          # 导出项目 ZIP（含元数据）
python workbench.py restore 归档.zip --dest 目标目录    # 还原导出包
python workbench.py rollback create --project 我的短片 --label 里程碑前   # 项目状态快照（state/参考记忆/状态卡/流程图）
python workbench.py rollback list --project 我的短片                 # 快照列表
python workbench.py rollback apply --project 我的短片 --snapshot <snap_id> [--dry-run]   # 回滚（回滚前自动安全快照）
python workbench.py validate 文件.json --schema state.schema.json
python workbench.py flow serve --project 我的短片      # 启动可视化节点工作台（打开打印的带 token URL）
    # 页面内置实时预览：每 1.2s 轮询 /api/dev/version，静态资源变更后自动刷新
python workbench.py flow new --project 我的短片 --name 从零到05   # 新建流程图骨架
python workbench.py flow list --project 我的短片
python workbench.py flow validate --project 我的短片 --graph flow-main
python workbench.py flow run --project 我的短片 --graph flow-main --dry-run   # 预演；--live 真实推进
python workbench.py flow templates --json                          # 模板库（4 套：从零到成片/启动接力/知识增强/风格注入）
python workbench.py flow new --project 我的短片 --template tpl-full-flow --name 从零到成片
python workbench.py flow runs --project 我的短片                   # 运行历史（含步骤/失败/恢复来源）
python workbench.py flow batch --project 我的短片 --all --dry-run --auto-retry 1  # 批量预演（失败图自动重试）
python workbench.py flow batches --project 我的短片                     # 批次历史（最近批次摘要）
python workbench.py flow batch-show --project 我的短片 --batch <batch_id>  # 批次详情（图/尝试/错误）
python workbench.py flow batch --project 我的短片 --all --dry-run --parallel --workers 2  # 并行预演（仅 dry-run，1–8 线程）
python workbench.py flow batch-recover --project 我的短片 --batch <batch_id>  # 重跑批次中的失败图并更新原批次
python workbench.py flow queue add --project 我的短片 --all --dry-run      # 加入批次队列（顺序执行）
python workbench.py flow queue list --project 我的短片                      # 查看队列（状态/图数/批次/失败通知）
python workbench.py flow queue run --project 我的短片 --limit 5             # 执行队列（跨项目用 --all-projects）
python workbench.py flow queue add --project 我的短片 --all --at 2026-11-15T20:00  # 定时入队（到点才执行）
python workbench.py flow queue cancel <queue_id> --project 我的短片             # 取消待运行条目
python workbench.py flow queue move <queue_id> --project 我的短片 --index 0      # 调整队列顺序（--before/--after/--index）
python workbench.py flow queue daemon --project 我的短片 --interval 30           # 后台守护：周期执行到期条目
python workbench.py flow queue daemon --project 我的短片 --cron "*/5 * * * *"   # cron 定时守护（5 段表达式，按分钟触发）
python workbench.py flow batch --project 我的短片 --all --dry-run --webhook-url http://localhost:9000/hook  # 批次失败外送 webhook
python workbench.py flow queue retry <queue_id> --project 我的短片              # 重置失败条目为待运行（下次执行）
python workbench.py flow queue notifications --project 我的短片 --limit 20    # 查看失败通知外送日志（JSONL）
python workbench.py flow recover --run <run_id> --project 我的短片 --yes   # 失败恢复（可加 --restore-state）
python workbench.py flow replay --run <run_id> --project 我的短片           # 运行回放（每步耗时/失败定位）
python workbench.py flow export --project 我的短片 --graph flow-main --out flow.json   # 导出流程图
python workbench.py flow import --project 我的短片 --file flow.json --graph imported-flow  # 导入流程图
python workbench.py flow diff --project 我的短片 --run <run_id> --other-run <run_id>      # 两次运行对比（状态/耗时/回归）
python workbench.py flow baseline set --project <项目> --run <run-id>   # 保存运行基线（回归对比）
python workbench.py project snapshot --project <项目>                  # 产物快照（差异视图）
python workbench.py project artifacts-diff --project <项目>            # 与最近快照对比
python workbench.py generate providers                        # 生成平台 4 provider（含 env key 状态）
python workbench.py generate plan --provider seedance_2_5 --prompt-file 05_shots/shot-01-prompt.md --shot 1-01   # 提交前预检
python workbench.py generate submit --provider minimax_h3 --prompt-file 05_shots/shot-01-prompt.md --live       # 真实提交（需环境变量 key）
python workbench.py generate jobs --project 我的短片 --limit 20   # 生成任务记录
python workbench.py generate show <job_id> --project 我的短片      # 任务详情
python workbench.py generate refresh --project 我的短片 --all    # 刷新所有 submitted 任务状态（查询平台）
python workbench.py generate refresh <job_id> --project 我的短片 # 查询单个任务并更新本地记录
python workbench.py generate retry <job_id> --project 我的短片         # 失败/取消任务重试（默认沿用原 dry-run/live 方式）
python workbench.py generate adopt <job_id> --project 我的短片 --stage 05  # 成功结果回填为项目产物（凭证 + state 登记）
python workbench.py generate adopt --all --project 我的短片 --stage 05   # 批量回填全部已成功任务
python workbench.py project summary --project 我的短片        # 项目摘要（产物/流程图/运行）
python workbench.py project list --stats                      # 跨项目统计（产物/待门禁/流程/运行）
python workbench.py flow run --project 我的短片 --graph flow-main --live --retries 2   # 节点失败自动重试（0–3）
python workbench.py index build --source <知识库子目录>   # 按契约重建索引（FTS5 trigram；--incremental 增量）
python workbench.py index search --query 第一幕 --limit 5  # 全文检索证据片段（短查询自动 LIKE 回退）
python workbench.py index verify                          # 校验索引库与元数据一致性
python workbench.py index health --source <知识库子目录>   # 健康巡检：结构/FTS/陈旧文件与修复建议（M29）
python workbench.py index health --out index --json        # 健康报告 JSON；存在问题退出码 1
python workbench.py index search --query 第一幕 --mode hybrid --limit 5   # 混合排序（标题/路径/短语加权，M24）
python workbench.py queue run --project 我的短片 --webhook-url https://example.com/hook  # 失败通知外送 webhook（M24）
python workbench.py index search --query 第一幕 --mode hybrid --weights heading=3,path=1,phrase=2,coverage=1  # 自定义检索权重（M27；也可 --config 指定配置）
python workbench.py index search --query 第一幕 --mode hybrid --min-score 2.5 --max-per-file 1  # 分数阈值与每文件条数控制（M30）
python workbench.py flow cron-preview --expression "*/5 * * * *" --count 3  # cron 表达式预览（下一次触发时间，M31）
python workbench.py flow queue alerts --project 我的短片 --limit 20         # 队列失败告警聚合（M31）
python workbench.py flow queue alerts --project 我的短片 --webhook-url https://example.test/hook  # 告警摘要外送（M32，event=queue.alerts.digest）
python workbench.py flow queue alerts --project 我的短片 --fail-if-failures                   # 存在失败通知时退出码 2（巡检/cron 判断，M32）
python workbench.py flow batch-report --project 我的短片 --format md --out batch-report.md   # 批次趋势报表 Markdown/CSV/HTML（M33/M35）
python workbench.py flow batch-report --project 我的短片 --format html --out batch-report.html   # 自包含 HTML 报告（M35）
python workbench.py flow batch-report --project 我的短片 --format md --push --webhook-url <url>   # 批次报表推送（M36；--webhook-format feishu 走飞书文本消息，--webhook-retries 0–3 退避重试）
python workbench.py flow batch-trend --project 我的短片 --out batch-trend.svg   # 批次趋势 SVG 图（自包含单文件，M37）
python workbench.py flow queue alerts --project 我的短片 --webhook-format feishu --webhook-url https://open.feishu.cn/open-apis/bot/v2/hook/<token>  # 飞书文本消息外送（M33）
python workbench.py project list --stats                            # 跨项目总览 + 流程/运行/待门禁/产物统计
```

- 项目默认创建在「文档目录/AI 影视工作台/projects/<名称>/」，可用 `--project-root` 或环境变量 `AI_FILM_PROJECTS_ROOT` 覆盖；包含 `00_project/`（状态、参考记忆、历史、知识卡、风格卡）、`00_inbox/`、`01_story/` … `06_prompts/`。
- 项目状态以 `00_project/state.json` 为唯一事实来源，必须通过 `state.schema.json`（v2 字段）校验；门禁与修订日志同文件持久化。
- 本地 CI：`python scripts/run_ci.py`（编译 → 文档链接检查 → FR 追溯映射 → 524 项测试 → 行覆盖率 ≥80% / 分支覆盖率 ≥50% → doctor → CLI 冷启动 NFR 基准 → brand-guard → 可复现构建校验；Python 3.11 跳过覆盖率门禁，仅 3.12 强制双门槛）。
- 文档链接检查：`python scripts/check_doc_links.py`（Markdown 链接与行内代码中的仓库内路径必须存在）。
- CLI 冷启动基准：`python scripts/bench.py`（默认 5 次取中位数，`--enforce` 时超过 1.0s 退出码 1）。
- 知识服务只读现有索引，不改知识库本体；先做元数据候选，召回不足时按预算做有限正文回退；只有路径/行号/命中词齐全才输出 `ok` 知识卡。回退可用 `--no-fallback` 关闭、用 `--fallback-files` / `--fallback-bytes` 调预算。证据按质量评分排序，并过滤「反转身」等动作误命中；高置信证据足够时会丢弃纯字面低置信证据（统计见 `report.evidence_quality`）。
- 风格服务只读引用外部 200 位导演色卡包（`scripts/build_style_registry.py` 生成注册表）；风格默认不注入：先 `style apply` 写风格卡与 `state.style`，再 `style inject` 做结构校验并写注入记录。校验只针对用户正文，风格卡作为提示词前缀；06 用图像工具、08 用视频工具，其他阶段不挂载。
- 生成发行清单：`python scripts/build_manifest.py`。
- 生成发行包：`python scripts/build_release.py`（输出 `dist/workbench-<版本>.zip` 与 SHA-256）。
- 发行包冒烟：`python scripts/package_smoke.py`（校验 `.sha256` → 解压到临时目录 → `version`/`doctor`/manifest 一致性；对应 PRD §11.3/§11.4）。
- 行覆盖率检查：`python scripts/coverage_check.py`（`packages/` 可执行行，CI `--min 80`；2.13.0 实测 80.84%（行），已达 PRD ≥80% 目标）。
- 分支覆盖率检查：`python scripts/coverage_check.py --branches --min-branches 50`（静态 `dis` 分支点 + 局部 `sys.monitoring` BRANCH 事件；2.13.0 实测 50.52%（2914/5768），CI 门禁 50%；覆盖率门禁仅在 Python 3.12+ 执行）。
- 可复现构建校验：`python scripts/repro_check.py`（两次构建与 `.sha256` 三方一致；`build_release.py` 固定 zip 时间戳/权限）。
- 跨平台 CI：`.github/workflows/ci.yml`（ubuntu/windows/macos × Python 3.11/3.12 矩阵，说明见 `docs/ci.md`）。
- 远端 CI 就绪检查：`python scripts/ci_ready.py`（工作流矩阵/步骤 + `git remote` 自检；`--require-remote` 供工作流使用）；真实远端执行需先按 `docs/github-actions.md` 配置 remote 并启用 Actions。

## 契约一览（contracts 1.0）

| 契约 | 文件 | 作用 |
|---|---|---|
| 项目状态 | `state.schema.json` | 入口/模式/阶段/版本/门禁/参考编号（v2 扩展：知识桥、风格、修订日志） |
| 跨阶段参考记忆 | `reference-memory.schema.json` | 参考方法条目与变更留痕 |
| 知识卡 | `knowledge-card.schema.json` | 检索画像、证据链、确认状态 |
| 风格画像 | `style-profile.schema.json` | 导演色卡、适配器、质量等级 |
| 风格注册表 | `style-registry.schema.json` | 200 位导演色卡元数据、质量分级与问题清单 |
| 阶段产物 | `stage-artifact.schema.json` | 产物版本、哈希、门禁、确认状态 |
| 阶段注册表 | `stage-registry.schema.json` | 8 阶段输入输出、门禁、挂载点 |
| 流程图 / 运行记录 / 节点类型 / 模板 | `flow-graph.schema.json`、`flow-run.schema.json`、`flow-node-types.schema.json`、`flow-templates.schema.json`、`flow-batch.schema.json` | 可视化节点工作流（v0.1，见 `docs/flow-workbench.md`） |
| 生成平台 | `generate-providers.schema.json`、`generate-job.schema.json` | 平台注册表（4 provider）与生成任务记录（v0.1，dry-run 默认） |
| 检索配置 | `knowledge-search.schema.json` | 检索权重、同义词、停用词与查询扩展上限（v0.1，M27） |

## 迭代状态

| 迭代 | 范围 | 状态 |
|---|---|---|
| 0 | 骨架、契约、注册表、品牌守卫、CLI、CI | 已完成（0.1.0） |
| 1a | B 知识服务 PoC：只读适配现库、证据链、知识卡、真实库实跑 | 已完成（0.2.0） |
| 2 | B 知识接入：召回改进方案 A——有限正文回退（只读、预算可配） | 已完成（0.3.0） |
| 2.1 | B 知识接入精度修订：动作误命中过滤、结构语境/叙事搭配/多词共现加权、低置信证据丢弃 | 已完成（0.3.1） |
| 1b | A 编排硬化：安装器、初始化器、路由、门禁、状态卡 v2、迁移 | 已完成（0.4.0） |
| 3 | C 风格服务：200 导演色卡 → 风格画像 → 多模型提示词适配与 06/08 注入记录 | 已完成（0.5.0） |
| 4 | 试点项目与发布：试点 A（从零到 08）、试点 B（B 入口到 05）、M1–M9 复核、文档定稿、1.0.0 发行包与回滚演练 | 已完成（1.0.0） |
| 1.0.1 | 真实项目补丁：产物登记 CLI、知识桥状态 CLI、跨阶段内容一致性检查、风格批量注入 API | 已完成（1.0.1） |
| 1.0.2 | 工作台体验补丁：跨项目总览（project list）、风格质量提示、批量逐镜注入记录、init 下一步引导 | 已完成（1.0.2） |
| M1（5） | 可视化节点工作台：流程图契约、节点类型注册表、执行引擎（拓扑/dry-run/确认断点）、flow 子命令、WebUI（画布/拖拽/连线/参数/运行） | 已完成（1.1.0） |
| M2+M3（6） | 可视化节点工作台能力层：10 类节点（知识检索/风格 apply+inject/产物登记/内容检查/导出）、4 套模板、运行历史与失败恢复、任意 DAG 与跳阶段、撤销重做、批量预演 | 已完成（1.2.0） |
| M4（7） | 可视化节点工作台体验：运行回放与耗时统计、失败节点定位、流程图 JSON 导入导出（CLI/Web/前端） | 已完成（1.3.0） |
| M5（8） | 可视化节点工作台增强：并行分支执行（仅只读节点）、节点级重试、跨项目管理面板（阶段/门禁/产物/流程/运行统计） | 已完成（1.4.0） |
| M6（9） | 可视化节点工作台加固：写状态节点文件锁与事务日志、两次运行 diff 对比、项目面板产物预览与流程图缩略图 | 已完成（1.5.0） |
| M7（10） | 可视化节点工作台控制流：条件分支/循环节点、运行基线保存与回归阈值告警（CI 闸门）、项目摘要缓存与产物快照差异视图 | 已完成（1.6.0） |
| M8（11） | 可视化节点工作台复合层：知识卡采纳/风格绑定复合节点、真实生成平台适配层（4 provider、任务记录、CLI/Web API、dry-run 默认） | 已完成（1.7.0） |
| M9（12） | 生成平台状态轮询与 Web 生成面板：任务状态查询/刷新（CLI+Web API）、provider 环境变量状态、任务列表按状态着色、预检与 dry-run 提交、批量刷新 | 已完成（1.8.0） |
| M10（13） | 生成结果回填与失败重试：succeeded 结果写凭证并登记项目产物（默认 05_shots）、failed/canceled 一键重试（`retried_from` 溯源）、Web 任务详情抽屉（详情/结果链接/重试/回填） | 已完成（1.9.0） |
| M11（14） | 生成平台扩展：批量回填（`generate adopt --all`/Web API/面板一键）、`generate_refresh`/`generate_adopt` 流程节点（节点 15→17 类）、生成面板按状态筛选 | 已完成（1.10.0） |
| 2.0.1（补丁） | 实时预览与界面迭代：`/api/dev/version` 静态签名 + 1.2s 轮询自动刷新、预览徽标、节点分类视觉（分类圆点/同色徽标/端口圆点/箭头连线）、17 类节点演示图（17 节点/26 连线）、2 项 dev 端点测试 | 已完成（2.0.1） |
| M12（15） | 批量运行编排：`flow batch` 批次记录（批次历史/详情）、失败图自动重试（`--auto-retry` 0–3）、失败即停（`--fail-fast`）、Web API `POST /api/workflows/batch` 与批次查询；`flow batch` JSON 输出改为批次信封（破坏性→2.0.0） | 已完成（2.0.0） |
| M13（16） | 批次增强：并行预演（`--parallel` / `--workers` 1–8，仅 dry-run；live 强制串行）、`flow batch-recover` 重跑失败图并把新尝试合并进原批次、批次恢复 Web API `POST /api/batches/<batch_id>/recover`、前端「恢复失败图」按钮、`flow-batch` 契约 v0.1 增加可选 `parallel`/`workers` | 已完成（2.1.0） |
| M14（17） | 批次队列化与失败通知：`flow queue add/list/run`（队列文件 `00_project/workflows/queue.json`，按创建顺序执行 pending 条目）、CLI 跨项目 `flow queue run --all-projects`、失败图汇总通知写回队列条目、Web API `POST /api/queue`/`POST /api/queue/run`/`GET /api/queue` 与前端队列列表；`flow-queue` 契约 v0.1 | 已完成（2.2.0） |
| M15（18） | 队列增强：`flow queue add --at` 定时执行（`scheduled_at`）、`flow queue cancel/move` 取消与重排（`order`）、`flow queue daemon --interval/--limit/--until-empty/--all-projects` 后台守护；Web API `POST /api/queue/<id>/cancel`、`POST /api/queue/<id>/move` 与前端队列顺序/计划时间操作；`flow-queue` 契约新增可选字段 | 已完成（2.3.0） |
| M16（19） | 队列重试与通知：`flow queue retry` 重置失败条目（`attempts` 计数）、`run --retry-failed N`/`daemon --retry-failed N` 自动重试、失败通知 JSONL（`00_project/workflows/queue-notifications.jsonl`）与 `--notify-cmd` 外部命令外送、`flow queue notifications` 查询、daemon `--log-file/--rotate-bytes` 日志轮转；Web API `GET /api/queue/notifications`、`POST /api/queue/<id>/retry` 与前端「重试」按钮 | 已完成（2.4.0） |
| M32（35） | 队列告警运维闭环：`flow queue alerts --webhook-url` 外送 `event=queue.alerts.digest` 摘要、`--fail-if-failures` 存在失败通知时退出码 2、Web 批次面板「恢复全部失败图」一键入口（最多 5 个批次）；新增 4 项测试合计 497 项 | 已完成（2.19.0） |
| M33（36） | 告警外送增强与批次趋势报表：`--webhook-format feishu`（飞书文本消息）与 `--webhook-retries 0–3`（固定退避重试）、`flow batch-report --format md/csv [--out]` 导出最近批次趋势；新增 12 项测试合计 509 项 | 已完成（2.20.0） |
| M34（37） | 批次报表 Web 化与告警静默窗口：Web `GET /api/batches/report`（md/csv）与批次面板「报表 MD/CSV/预览」按钮；`flow queue alerts --dedupe-minutes`（相同告警静默窗口去重，0 关闭）；新增 3 项测试合计 512 项 | 已完成（2.21.0） |
| M35（38） | 批次报表 HTML 化：`flow batch-report --format html` 生成自包含 HTML 报告（内联 CSS、汇总卡片、趋势条、明细表）；`GET /api/batches/report?format=html` 与批次面板「报表 HTML」按钮；新增 1 项测试合计 513 项 | 已完成（2.22.0） |
| M36（39） | 批次报表推送与告警静默窗口状态：`flow batch-report --push --webhook-url <url>`（`event=batch.report`，复用飞书格式与 `--webhook-retries`）；Web `POST /api/batches/report/push` 与批次面板「推送报表」按钮；`GET /api/queue/alerts` 新增 `state`（上次外送/静默截止/是否静默中）并在 Web 告警面板展示；新增 5 项测试合计 518 项 | 已完成（2.23.0） |
| M37（40） | 飞书卡片通知与批次趋势 SVG：`--webhook-format feishu_card`（告警红/报表绿卡片）、`flow batch-trend --out trend.svg`、`GET /api/batches/trend` 与 Web「趋势 SVG」按钮；新增 6 项测试、全量 524 项 | 已完成（2.24.0） |
| M31（34） | 批次/队列运维收尾：`flow cron-preview`（5 段 cron 表达式预览下一次触发时间）、`flow queue alerts`（失败通知聚合：条数/最近消息/失败图 Top5）、Web API `POST /api/cron/preview` 与 `GET /api/queue/alerts`、前端批次历史趋势图（SVG）与失败告警面板；新增 5 项测试合计 493 项 | 已完成（2.18.0） |
| M30（33） | 检索结果精细化（M30）：`knowledge-search` 契约新增可选 `min_score`（≥0，0 不过滤）、`max_per_file`（1–10，默认 2）、`snippet_chars`（40–400，默认 120）、`proximity_weight`（0–2，默认 0.5）；hybrid 排序加入查询词邻近度加权，结果统一做分数过滤/每文件上限/片段截断；CLI `index search --min-score/--max-per-file`；`index_service` 报告同步配置；新增 9 项测试合计 488 项 | 已完成（2.17.0） |
| M29（32） | 索引健康巡检（`index health`：元数据/文档/FTS 一致性、无主分块、空分块、重复路径、可选源目录新增/变更/删除陈旧度与修复建议，问题时退出码 1）+ 同义词权重联动（`knowledge-search` 契约新增可选 `synonym_weight`，hybrid 词项覆盖率按原词 1.0 / 扩展词可配 0–1 加权，`index search` 输出 `term_weights`/`synonym_weight`）；新增 9 项测试合计 479 项 | 已完成（2.16.0） |
| M28（31） | 队列运维增强：`flow queue daemon --cron`（5 段 cron 按分钟触发，记录 last fired 防同分钟重复，保留 `--interval` 模式）、批次失败 webhook（`flow batch --webhook-url`，失败汇总 JSON POST `event=batch.run`，失败不阻断批次）、Web 批次历史面板（`loadBatches` 展示最近 10 个批次，失败行「恢复失败图」→ `POST /api/batches/<id>/recover`）；新增 11 项测试合计 470 项 | 已完成（2.15.0） |
| M27（30） | 索引检索配置增强：`knowledge-search` 契约 + `content/knowledge-search.json`（权重 heading/path/phrase/coverage、8 组同义词、13 个停用词、expand_limit 8）、`load_search_config`/`normalize_query_text`/同义词查询扩展、`index search --config/--weights`、doctor 要求 2 份索引契约；新增 17 项测试合计 459 项 | 已完成（2.14.0） |
| M26（29） | 远端 CI 工作流硬化与就绪检查：`.github/workflows/ci.yml` 增加 `permissions/concurrency/timeout-minutes/PYTHONIOENCODING` 与 readiness 步骤（`ci_ready.py --require-remote`）；新增 `scripts/ci_ready.py`（矩阵/步骤自检 + git remote 检测，`--json/--require-remote`）与 `docs/github-actions.md` 接入指南；新增 8 项测试合计 442 项 | 已完成（2.13.1 PATCH） |
| M25（28） | 分支覆盖率门禁：`coverage_check.py` 新增 `--branches/--min-branches`（`dis` 静态分支点 + 局部 `sys.monitoring` BRANCH 事件，只监控 `packages` 模块 code 对象），`run_ci.py` 覆盖率步骤改为 `--min 80 --branches --min-branches 50`；新增 5 项测试合计 434 项 | 已完成（2.13.0） |
| M24（27） | 索引混合排序与队列 webhook 通知：`index search --mode auto|fts|like|hybrid`（默认 hybrid：标题/路径/短语/词项覆盖率加权，FTS+LIKE 候选按文件+标题去重后按分数降序）；`index_service` 证据卡改用 hybrid 排序；`queue run/daemon --webhook-url` 失败汇总 JSON POST（失败不阻断队列、未配置 no-op）；新增 9 项测试合计 429 项 | 已完成（2.12.0） |
| M23（26） | 覆盖率提升与 80% 门禁：新增 `tests/test_cli_coverage.py`（6 组 in-process CLI 广覆盖：项目快照/回滚、流程图导出导入与运行/回放/差异/基线、批次与队列全流程、索引构建/检索、generate 命令行）与 `tests/test_webui_api.py::test_http_error_paths`（404/400/501 分支）；行覆盖率 77.37%→80.8%（6284/7777 行），CI 覆盖率门禁 `--min 75`→`80`；全量 420 项测试 | 已完成（2.11.0） |
| M22（25） | 本地索引接入知识服务：`packages/knowledge_service/index_service.py`（`search_index_card` 逐查询 FTS/LIKE、证据四字段去重排序、knowledge-card 契约校验、no_evidence）+ CLI `knowledge search --index` + flow `knowledge_search` 节点新增可选 `index` 参数；索引不可用时保持原外部知识库路径 | 已完成（2.10.0） |
| M21（24） | 知识库索引维护（FR-10）：`packages/knowledge_service/index_builder.py`（SQLite FTS5 trigram、分块 900/重叠 80、全量+增量构建、契约校验）+ CLI `index build/info/verify/search` + `doctor` 索引检查（10 项） + `knowledge-index.schema.json`；索引产物默认 `index/`（不入发行包） | 已完成（2.9.0） |
| M20（23） | 跨平台 CI、覆盖率与可复现构建门禁、Web 快照回滚：`.github/workflows/ci.yml` 三平台 × 双 Python 矩阵；`scripts/coverage_check.py`（零依赖行覆盖率 76.37%，CI `--min 75`）；`scripts/repro_check.py` + `build_release.py` 固定时间戳（两次构建一致）；Web `/api/rollback/*` 与前端快照/回滚面板 | 已完成（2.8.0） |
| M19（22） | 需求追溯与 FR↔里程碑映射：新增 `docs/requirements-traceability.md`（FR-01–FR-22 ↔ 实现/里程碑/证据/状态）与 `scripts/check_fr_mapping.py`（覆盖/重复/PRD 交叉校验，纳入 CI，门禁扩为七步） | 已完成（2.7.0） |
| M18（21） | 项目状态快照与回滚：`workbench.py rollback create/list/apply`（`00_project/history/snapshots/<snap-id>.zip` 快照 state/参考记忆/状态卡/流程图；回滚前自动安全快照、`--dry-run` 预演、路径校验）；`scripts/rollback_drill.py` 发行包升级→回滚演练（上一版→最新→回滚上一版并校验版本）；PRD §11.4 rollback 落地 | 已完成（2.6.0） |
| M17（20） | PRD 验收对齐：打包冒烟（`scripts/package_smoke.py`：SHA256→解压→version/doctor/manifest）、文档链接检查（`scripts/check_doc_links.py` 纳入 CI）、CLI 冷启动 NFR 基准（`scripts/bench.py`）、PRD §2.5 指标扩展/§11 验收与 E2E 扩展/文档一致性修订 | 已完成（2.5.0） |

## 原则

- **单阶段推进**：任一时刻只执行一个阶段，不跨阶段串写。
- **确认点前置**：入口、定位菜单、镜头规划、风格卡、知识卡都必须先展示再等待确认。
- **知识桥不是阶段**：默认关闭，只有用户明确请求才检索；没有本地路径/页码/命中词不得声称命中。
- **修订留版本**：先写新版本，再让下游读取最新已确认版本；上游变更必须标记受影响下游。
- **品牌中性**：所有产出与文档不得出现历史品牌字样；例外仅限第三方语料本体（见 `docs/brand-guard.md`）。
- **可视化只是编排层**：流程图不替代 `state.json`；节点执行复用既有服务层，结果仍写回状态卡（见 `docs/flow-workbench.md`）。

## 文档

- `docs/quick-start.md`：第一次拿到发行包的 10 分钟上手（自检/建项目/阶段推进/知识/风格）。
- `docs/flow-workbench.md`：可视化节点工作台（M1–M16 + 2.0.1 实时预览，含条件/循环、基线、产物快照、复合节点、生成平台、任务状态轮询、结果回填与任务详情、批量批次编排与自动重试、批次并行预演与失败图恢复、批次队列与失败通知、队列定时调度/取消重排/后台守护、队列失败重试与通知外送、M22 索引证据卡接入）：架构、17 类节点与端口、模板库、运行历史与恢复、批量运行、Web API、前端交互、安全边界与限制（M17/M18/M20 的验收工具链、项目快照/回滚与跨平台 CI/覆盖率门禁见 `docs/architecture.md`、`docs/command-card.md`、`docs/ci.md` 与 `docs/release-notes-2.6.0.md`）。
- `docs/release-notes-1.0.0.md`：1.0.0 发行说明（能力、验证、限制、升级与校验）。
- `docs/release-notes-1.0.1.md`：1.0.1 补丁说明（P2 四项修复、接口、测试与升级方式）。
- `docs/release-notes-1.0.2.md`：1.0.2 补丁说明（跨项目总览、风格质量提示、逐镜注入记录、init 引导）。
- `docs/release-notes-1.3.0.md`：1.3.0 发行说明（M4 回放与图导入导出、验证、升级与限制）。
- `docs/release-notes-1.4.0.md`：1.4.0 发行说明（M5 并行执行、节点级重试、项目管理面板）。
- `docs/release-notes-1.5.0.md`：1.5.0 发行说明（M6 状态锁与事务、运行对比、项目预览）。
- `docs/release-notes-1.6.0.md`：1.6.0 发行说明（M7 条件分支/循环、运行基线与回归告警、产物快照）。
- `docs/release-notes-1.7.0.md`：1.7.0 发行说明（M8 复合节点、生成平台适配层、CLI/Web API 与 dry-run）。
- `docs/release-notes-1.8.0.md`：1.8.0 发行说明（M9 生成任务状态轮询、Web 生成面板、批量刷新）。
- `docs/release-notes-1.9.0.md`：1.9.0 发行说明（M10 生成结果回填、失败重试、任务详情抽屉）。
- `docs/release-notes-1.10.0.md`：1.10.0 发行说明（M11 批量回填、生成平台流程节点、生成面板筛选）。
- `docs/release-notes-2.0.0.md`：2.0.0 发行说明（M12 批量批次编排、自动重试、批次历史、验证、升级与限制）。
- `docs/release-notes-2.0.1.md`：2.0.1 发行说明（实时预览 `/api/dev/version`、自动刷新、界面视觉与 17 类节点演示、验证与限制）。
- `docs/release-notes-2.1.0.md`：2.1.0 发行说明（批次并行预演、失败图一键恢复、验证与限制）。
- `docs/release-notes-2.2.0.md`：2.2.0 发行说明（M14 批次队列化、失败通知、CLI/Web/前端队列、验证与限制）。
- `docs/release-notes-2.3.0.md`：2.3.0 发行说明（M15 队列定时调度、取消/重排、后台守护、验证与限制）。
- `docs/release-notes-2.4.0.md`：2.4.0 发行说明（M16 队列失败重试、通知外送与守护日志轮转、验证与限制）。
- `docs/release-notes-2.5.0.md`：2.5.0 发行说明（M17 PRD 验收对齐：打包冒烟、文档链接检查、CLI 冷启动 NFR 基准、PRD 指标/验收与文档一致性修订、验证与限制）。
- `docs/release-notes-2.6.0.md`：2.6.0 发行说明（M18 项目状态快照与回滚：`rollback` 子命令、安全快照、dry-run、发行包回滚演练、验证与限制）。
- `docs/release-notes-2.7.0.md`：2.7.0 发行说明（M19 需求追溯：FR↔里程碑映射表与 CI 映射检查、验证与限制）。
- `docs/release-notes-2.8.0.md`：2.8.0 发行说明（M20 跨平台 CI 矩阵、覆盖率与可复现构建门禁、Web 快照回滚面板、验证与限制）。
- `docs/release-notes-2.9.0.md`：2.9.0 发行说明（M21 知识库索引维护：按契约重建/增量索引、FTS5 trigram 检索、验证与限制）。
- `docs/release-notes-2.10.0.md`：2.10.0 发行说明（M22 本地索引接入知识服务证据卡：`search_index_card`、CLI `--index`、flow 节点参数、验证与限制）。
- `docs/release-notes-2.11.0.md`：2.11.0 发行说明（M23 覆盖率提升至 80.8%、CI 门禁升至 80%、新增 CLI 广覆盖与 Web 错误路径测试）。
- `docs/release-notes-2.12.0.md`：2.12.0 发行说明（M24 索引混合排序 `--mode hybrid`、队列 webhook 通知 `--webhook-url`、验证与限制）。
- `docs/release-notes-2.13.0.md`：2.13.0 发行说明（M25 分支覆盖率门禁：`--branches`、局部 BRANCH 事件、行 80.84%/分支 50.52%、CI 门槛 50%）。
- `docs/release-notes-2.13.1.md`：2.13.1 发行说明（M26 远端 CI 工作流硬化与 `ci_ready.py` 就绪检查；真实远端执行待配置 remote）。
- `docs/release-notes-2.14.0.md`：2.14.0 发行说明（M27 索引检索配置增强：权重/同义词/停用词与 hybrid 查询扩展、验证与限制）。
- `docs/release-notes-2.15.0.md`：2.15.0 发行说明（M28 队列运维增强：cron 定时守护、批次失败 webhook、Web 批次历史面板）。
- `docs/release-notes-2.16.0.md`：2.16.0 发行说明（M29 索引健康巡检与同义词权重：`index health`、`synonym_weight`）。
- `docs/release-notes-2.17.0.md`：2.17.0 发行说明（M30 检索结果精细化：分数阈值、每文件上限、片段长度、邻近度加权）。
- `docs/release-notes-2.18.0.md`：2.18.0 发行说明（M31 批次/队列运维收尾：cron 预览、批次趋势图、失败告警聚合）。
- `docs/release-notes-2.19.0.md`：2.19.0 发行说明（M32 队列告警运维闭环：告警摘要 webhook 外送、巡检退出码、Web 一键恢复全部失败批次）。
- `docs/release-notes-2.20.0.md`：2.20.0 发行说明（M33 告警外送增强：webhook 重试/退避与飞书文本格式；批次趋势报表 `flow batch-report` Markdown/CSV）。
- `docs/release-notes-2.21.0.md`：2.21.0 发行说明（M34 批次报表 Web 化：`GET /api/batches/report` 与面板预览/导出；告警静默窗口 `queue alerts --dedupe-minutes`）。
- `docs/release-notes-2.22.0.md`：2.22.0 发行说明（M35 批次报表 HTML 化：自包含 HTML 报告、CLI/Web `--format html` 与面板「报表 HTML」按钮）。
- `docs/release-notes-2.23.0.md`：2.23.0 发行说明（M36 批次报表推送与告警静默窗口状态：`flow batch-report --push`、飞书/重试、Web 批次面板「推送报表」、告警 state 展示）。
- `docs/pilot-c-report.md`：真实项目试点报告（《死亡外科医生》从零到 done、M1–M9、摩擦与 1.0.x 清单）。
- `docs/architecture.md`：分层、数据流、阶段加载顺序、与现有 Skill 子系统的映射。
- `docs/command-card.md`：全部命令速查（环境、项目、迁移、安装、知识、风格、可视化工作流、契约）。
- `docs/requirements-traceability.md`：PRD §6 FR-01–FR-22 ↔ 实现/里程碑/证据映射（M19；`scripts/check_fr_mapping.py` 校验）。
- `docs/knowledge-index.md`：知识库索引维护（M21：契约、`index` 命令、分块与增量策略、FTS5/规模与限制；M22：索引接入知识服务证据卡——`search_index_card`、CLI `--index`、flow 节点 `index` 参数；M27：检索配置——权重/同义词/停用词与查询扩展；M29：健康巡检 `index health` 与 `synonym_weight` 词项加权；M30：结果阈值 `min_score`、每文件上限 `max_per_file`、片段长度 `snippet_chars` 与邻近度加权 `proximity_weight`）。
- `docs/ci.md`：CI 九步门禁、GitHub Actions 跨平台矩阵、本地等价命令、覆盖率策略与可复现构建（M20）。
- `docs/github-actions.md`：远端 CI 接入指南（M26：remote/Actions 启用、矩阵与耗时、artifact、排障）。
- `docs/troubleshooting.md`：故障排查（环境、门禁、风格、知识、编码、迁移、导出）。
- `docs/knowledge-service.md`：知识服务接口、只读保证与已知局限。
- `docs/knowledge-poc-report.md`：迭代 1a PoC 报告（探测、实跑证据、召回率决策）。
- `docs/iteration-2-recall-report.md`：迭代 2 方案 A 报告（有限正文回退、预算、真实库召回、精度观察与 0.3.1 精度修订实测）。
- `docs/iteration-1b-report.md`：迭代 1b 报告（安装器/初始化器/意图路由/门禁/状态卡 v2/迁移与 E2E 证据）。
- `docs/style-service.md`：风格服务接口、工具适配矩阵、注入记录与已知局限。
- `docs/style-registry-report.md`：风格包构建报告（质量分级与问题清单）。
- `docs/iteration-3-report.md`：迭代 3 报告（C 风格服务 0.5.0，注册表/风格卡/适配器/注入 E2E）。
- `docs/migration.md`：旧项目迁移与规则升级说明（字段映射、备份、回滚、检查清单）。
- `docs/iteration-4-report.md`：迭代 4 报告（试点 A/B、M1–M9、E2E-01~10、发布检查、回滚演练）。
- `docs/pilots/`：试点日志与指标（`pilot-a.json`、`pilot-b.json`、`metrics.json`）。
- `docs/pilot-c-trial-log-template.md`：试点 C 真实项目试用记录表（每日 4 指标 + 每周汇总）。
- `docs/brand-guard.md`：禁用词表、归一化、例外与 CI 阻断规则。
- `docs/iteration-0-report.md`：迭代 0 交付与验收记录。
- `AI影视工作台开发PRD.md`（工作区根）：完整产品需求与迭代计划。
