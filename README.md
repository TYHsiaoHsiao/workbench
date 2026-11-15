# AI 影视工作台（workbench）

把一个「剧本到视频提示词」的创作流程，从一堆提示词与 Skill 文件，升级成可执行、可校验、可交接的工作台。

- **8 个创作阶段**（01 概念锚定 → 08 视频提示词）由路由表统一描述；
- **知识服务**与**风格服务**作为可选挂载点，默认关闭、按需启用；
- **契约先行**：阶段产物、参考记忆、知识卡、风格画像、项目状态全部有 JSON Schema；
- **品牌守卫**：仓库与工作区零品牌残留，CI 阻断回归。

当前版本 `1.8.0`：迭代 0（地基）、迭代 1a（B 知识服务 PoC）、迭代 2 方案 A（有限正文回退）、迭代 2.1（精度修订）、迭代 1b（A 编排硬化）、迭代 3（C 风格服务）、迭代 4（试点与固化）、1.0.1（真实项目补丁）、1.0.2（工作台体验补丁）、M1（可视化节点工作台骨架，1.1.0）、M2/M3（可视化节点工作台能力层，1.2.0）、M4（运行回放与图导入导出，1.3.0）与 M5（并行执行、节点级重试、项目管理面板，1.4.0）与 M6（状态锁与事务、运行对比、项目预览，1.5.0）以及 M7（条件分支与循环、运行基线与回归告警、产物快照差异，1.6.0）与 M8（复合节点与真实生成平台适配，1.7.0）以及 M9（生成任务状态轮询与 Web 生成面板，1.8.0）已完成。三个试点：从零到 08（`试点A-雨夜回声`）、既有剧本到 05（`试点B-旧剧本接管`）、真实项目从零到 done（《死亡外科医生》，见 `docs/pilot-c-report.md`），指标与证据见 `docs/pilots/`。

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
    flow-node-types.json     # 可视化节点类型注册表 v0.1：15 类节点、端口与参数 schema
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
  tests/                     # 294 个 unittest 用例
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
python workbench.py validate 文件.json --schema state.schema.json
python workbench.py flow serve --project 我的短片      # 启动可视化节点工作台（打开打印的带 token URL）
python workbench.py flow new --project 我的短片 --name 从零到05   # 新建流程图骨架
python workbench.py flow list --project 我的短片
python workbench.py flow validate --project 我的短片 --graph flow-main
python workbench.py flow run --project 我的短片 --graph flow-main --dry-run   # 预演；--live 真实推进
python workbench.py flow templates --json                          # 模板库（4 套：从零到成片/启动接力/知识增强/风格注入）
python workbench.py flow new --project 我的短片 --template tpl-full-flow --name 从零到成片
python workbench.py flow runs --project 我的短片                   # 运行历史（含步骤/失败/恢复来源）
python workbench.py flow batch --project 我的短片 --all --dry-run  # 批量预演
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
python workbench.py project summary --project 我的短片        # 项目摘要（产物/流程图/运行）
python workbench.py project list --stats                      # 跨项目统计（产物/待门禁/流程/运行）
python workbench.py flow run --project 我的短片 --graph flow-main --live --retries 2   # 节点失败自动重试（0–3）
python workbench.py project list --stats                            # 跨项目总览 + 流程/运行/待门禁/产物统计
```

- 项目默认创建在「文档目录/AI 影视工作台/projects/<名称>/」，可用 `--project-root` 或环境变量 `AI_FILM_PROJECTS_ROOT` 覆盖；包含 `00_project/`（状态、参考记忆、历史、知识卡、风格卡）、`00_inbox/`、`01_story/` … `06_prompts/`。
- 项目状态以 `00_project/state.json` 为唯一事实来源，必须通过 `state.schema.json`（v2 字段）校验；门禁与修订日志同文件持久化。
- 本地 CI：`python scripts/run_ci.py`（编译 → 294 项测试 → doctor → brand-guard）。
- 知识服务只读现有索引，不改知识库本体；先做元数据候选，召回不足时按预算做有限正文回退；只有路径/行号/命中词齐全才输出 `ok` 知识卡。回退可用 `--no-fallback` 关闭、用 `--fallback-files` / `--fallback-bytes` 调预算。证据按质量评分排序，并过滤「反转身」等动作误命中；高置信证据足够时会丢弃纯字面低置信证据（统计见 `report.evidence_quality`）。
- 风格服务只读引用外部 200 位导演色卡包（`scripts/build_style_registry.py` 生成注册表）；风格默认不注入：先 `style apply` 写风格卡与 `state.style`，再 `style inject` 做结构校验并写注入记录。校验只针对用户正文，风格卡作为提示词前缀；06 用图像工具、08 用视频工具，其他阶段不挂载。
- 生成发行清单：`python scripts/build_manifest.py`。
- 生成发行包：`python scripts/build_release.py`（输出 `dist/workbench-<版本>.zip` 与 SHA-256）。

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
| 流程图 / 运行记录 / 节点类型 / 模板 | `flow-graph.schema.json`、`flow-run.schema.json`、`flow-node-types.schema.json`、`flow-templates.schema.json` | 可视化节点工作流（v0.1，见 `docs/flow-workbench.md`） |
| 生成平台 | `generate-providers.schema.json`、`generate-job.schema.json` | 平台注册表（4 provider）与生成任务记录（v0.1，dry-run 默认） |

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

## 原则

- **单阶段推进**：任一时刻只执行一个阶段，不跨阶段串写。
- **确认点前置**：入口、定位菜单、镜头规划、风格卡、知识卡都必须先展示再等待确认。
- **知识桥不是阶段**：默认关闭，只有用户明确请求才检索；没有本地路径/页码/命中词不得声称命中。
- **修订留版本**：先写新版本，再让下游读取最新已确认版本；上游变更必须标记受影响下游。
- **品牌中性**：所有产出与文档不得出现历史品牌字样；例外仅限第三方语料本体（见 `docs/brand-guard.md`）。
- **可视化只是编排层**：流程图不替代 `state.json`；节点执行复用既有服务层，结果仍写回状态卡（见 `docs/flow-workbench.md`）。

## 文档

- `docs/quick-start.md`：第一次拿到发行包的 10 分钟上手（自检/建项目/阶段推进/知识/风格）。
- `docs/flow-workbench.md`：可视化节点工作台（M1–M9，含条件/循环、基线、产物快照、复合节点、生成平台与任务状态轮询）：架构、15 类节点与端口、模板库、运行历史与恢复、批量运行、Web API、前端交互（撤销/重做/参数编辑/运行回放/JSON 导入导出/生成面板）、安全边界与限制。
- `docs/release-notes-1.0.0.md`：1.0.0 发行说明（能力、验证、限制、升级与校验）。
- `docs/release-notes-1.0.1.md`：1.0.1 补丁说明（P2 四项修复、接口、测试与升级方式）。
- `docs/release-notes-1.0.2.md`：1.0.2 补丁说明（跨项目总览、风格质量提示、逐镜注入记录、init 引导）。
- `docs/release-notes-1.3.0.md`：1.3.0 发行说明（M4 回放与图导入导出、验证、升级与限制）。
- `docs/release-notes-1.4.0.md`：1.4.0 发行说明（M5 并行执行、节点级重试、项目管理面板）。
- `docs/release-notes-1.5.0.md`：1.5.0 发行说明（M6 状态锁与事务、运行对比、项目预览）。
- `docs/release-notes-1.6.0.md`：1.6.0 发行说明（M7 条件分支/循环、运行基线与回归告警、产物快照）。
- `docs/release-notes-1.7.0.md`：1.7.0 发行说明（M8 复合节点、生成平台适配层、CLI/Web API 与 dry-run）。
- `docs/release-notes-1.8.0.md`：1.8.0 发行说明（M9 生成任务状态轮询、Web 生成面板、批量刷新）。
- `docs/pilot-c-report.md`：真实项目试点报告（《死亡外科医生》从零到 done、M1–M9、摩擦与 1.0.x 清单）。
- `docs/architecture.md`：分层、数据流、阶段加载顺序、与现有 Skill 子系统的映射。
- `docs/command-card.md`：全部命令速查（环境、项目、迁移、安装、知识、风格、可视化工作流、契约）。
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
