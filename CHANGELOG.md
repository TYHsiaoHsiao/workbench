# 变更日志

## [2.0.1] - 2026-11-15 — 实时预览与界面迭代（PATCH）

- 实时预览：新增 `GET /api/dev/version`（静态资源签名 = 文件:大小:mtime_ns + latest_mtime_ns），前端 `startLivePreview()` 每 1.2s 轮询，签名变化时提示并整页刷新；状态栏「● 实时预览」标识。
- 界面：节点按分类着色（分类圆点 + 同色类型徽标）、端口连接圆点、连线贝塞尔箭头与悬停高亮。
- 演示：预览演示项目新增「17 类节点演示」流程图（17 节点 / 26 连线，覆盖全部节点类型，经图校验）。
- 测试：新增 2 项 Web API 测试（dev 版本端点、静态文件变更签名变化），全量 325 项通过。
- 兼容性：PATCH 版本，无契约与 CLI 行为变更；实时预览仅影响浏览器端刷新。

## [2.0.0] - 2026-11-15 — 可视化节点工作台（M12：批量批次编排、批量自动重试与批次历史）

- 批次引擎：新增 `packages/flow/batch.py` 与 `flow-batch` 契约（v0.1）；`run_batch()` 逐图运行并把批次记录写入 `00_project/workflows/batches/<batch_id>.json`；失败图按 `auto_retry`（0–3）自动重试（每次新 run_id），`fail_fast` 首败即停、`limit` 限制图数量；summary 统计成功/失败/等待确认/跳过/尝试次数/总耗时。
- CLI：`flow batch` 改用批次引擎，JSON 输出由 `{count,results}` 改为 `{ok,project,batch}`（破坏性变更）；新增 `--auto-retry`/`--fail-fast`/`--limit`；新增 `flow batches` 与 `flow batch-show`。
- Web API：新增 `POST /api/workflows/batch`、`GET /api/batches`、`GET /api/batches/<batch_id>`；`POST /api/runs/batch` 保留为兼容别名（返回旧 `count`/`results` 字段）。
- 前端：批量预演改调新端点，逐图显示尝试次数/耗时/错误，完成状态含批次 ID。
- doctor：flow 契约检查补 `flow-batch.schema.json`（5 份）；contracts 共 14 份。
- 测试：新增 7 项（批次引擎 6、Web API 1），全量 323 项通过。
- 兼容性：`flow batch --json` 的输出结构变化为破坏性变更，故主版本升 2.0.0；流程图、state、其他 CLI/Web 接口不变。

## [1.10.0] - 2026-11-15 — 可视化节点工作台（M11：批量回填、生成平台流程节点与生成面板筛选）

- 批量回填：`adopt_all()` 扫描 succeeded 且未回填任务逐条回填，最后组合登记 `state.stage_artifacts`（逐条 adopt 会覆盖摘要）；CLI `generate adopt --all [--limit]`，Web API `POST /api/generate/jobs/adopt`，生成面板「回填全部已成功」。
- 生成平台流程节点：新增 `generate_refresh`（查询/刷新状态）与 `generate_adopt`（回填结果），节点类型 15→17，参数 `job_id` 或 `all=true`，dry-run 只计划；EXECUTORS 17 项。
- 生成面板筛选：任务列表按状态筛选（全部/排队中/成功/失败/已取消/dry-run/计划/已回填）。
- 测试：新增 10 项（批量回填 3、生成节点 6、批量回填 Web API 1），全量 316 项通过。
- 兼容性：复用既有 `generation`/`artifact`/`state` 端口，无新契约；旧流程图与节点参数不受影响。

## [1.9.0] - 2026-11-15 — 可视化节点工作台（M10：生成结果回填、失败重试与任务详情抽屉）

- 结果回填：`packages/generate/providers.py` 新增 `result_url()`（从任务 response 提取 video_url/output_url/嵌套 data 等结果 URL 与 `adopt()`（仅 succeeded 且未回填；在 `<阶段目录>/generations/shot-XX__<job_id>.json` 写结果凭证，经 `register_artifacts` 登记 `state.stage_artifacts`，任务记录写 `adopted`）。
- 失败重试：新增 `retry()`（仅 failed/canceled；按原 provider/模型/提示词创建新任务并记录 `retried_from`；默认沿用原任务提交方式，可传 `live` 覆盖）。
- 契约：`generate-job` 增加可选 `retried_from`（pattern）与 `adopted`（artifact+at），向后兼容。
- CLI：「generate retry <job_id>」与「generate adopt <job_id>」（`--stage` 默认 05、`--kind`、`--note`）。
- Web API：`POST /api/generate/jobs/<job_id>/retry`（body: project/live）、`POST /api/generate/jobs/<job_id>/adopt`（body: project/stage/kind/note）。
- Web 前端：生成面板任务表增加「详情」任务详情抽屉（状态/重试来源/回填结果/错误/任务 JSON），并提供「重试」「回填」按钮；顶栏「生成…」面板样式完善。
- 测试：新增 12 项（重试/回填 10、Web API 2），合计 306 项通过；doctor 9 项、本地 CI 全绿、品牌守卫 0 命中。
- 兼容：契约仍为 1.0；回填只登记凭证 JSON，重试不自动退避/轮询。

## [1.8.0] - 2026-11-15 — 可视化节点工作台（M9：生成任务状态轮询与 Web 生成面板）

- 任务状态查询：`packages/generate/providers.py` 新增 `_http_status()`（按 provider `status_path` 查询平台，Bearer 认证，平台外部 ID 从任务 `response` 提取）与 `refresh()`（平台状态归一为 running/succeeded/failed，终态任务短路返回，dry-run 与 mock 任务拒绝查询）、`refresh_all()`（批量刷新 submitted 任务，单任务失败不影响其他任务）；`generate` 包导出 `refresh` / `refresh_all`。
- CLI：新增 `generate refresh <job_id>` 与 `generate refresh --all`（`--project` 必填，支持 `--limit` / `--json`）。
- Web API：新增 `POST /api/generate/jobs/<job_id>/refresh` 与 `POST /api/generate/jobs/refresh`；`GET /api/generate/providers` 每项增加 `env_set` 字段。
- Web 前端：顶栏「生成…」打开生成面板——provider 与 env key 状态、任务表（状态着色 / dry-run 标记）、预检、提交（live 需确认）、单任务刷新与「刷新全部 submitted」。
- 测试：新增 11 项（状态查询 9、Web API 2），合计 294 项通过；doctor 9 项、本地 CI 全绿、品牌守卫 0 命中。
- 兼容：契约不变（flow/generate 仍为 v0.1）；轮询是显式动作，默认不后台请求平台。

## [1.7.0] - 2026-11-15 — 可视化节点工作台（M8：复合节点与生成平台适配层）

- 复合节点：新增 `knowledge_adopt`（读取已确认知识卡，把证据逐条写入参考记忆并同步 `state.references` / 知识桥状态；重复证据去重）与 `style_bind`（把风格画像绑定为 `style_reference` 参考记忆，默认 scope image_06/camera_08）。
- 生成平台适配层：新增 `packages/generate`（`providers.py` 注册表加载与计划/提交；`jobs.py` 任务记录，存 `00_project/generations/jobs/`）；内置 mock / seedance_2_0 / seedance_2_5 / minimax_h3 四个 provider；默认 dry-run，只有 `--live` 且环境变量 key 存在时才真实提交（urllib，无第三方依赖）。
- 契约：新增 `generate-providers.schema.json` 与 `generate-job.schema.json`（v0.1）；节点类型 12→15（`knowledge_adopt` / `style_bind` / `generate`），新增 `reference` / `generation` 端口与 PORT_COMPAT 兼容。
- CLI/Web：`generate providers/plan/submit/jobs/show` 子命令；Web API `GET /api/generate/providers`、`POST /api/generate/plan`、`POST /api/generate/jobs`、`GET /api/generate/jobs[/<id>]`；前端节点库与端口连线自动支持 15 类节点；doctor 新增 generate 检查（9 项全 OK）。
- 测试：新增 21 项（generate 适配层、复合节点、Web API），合计 283 项通过；doctor 9 项、本地 CI 全绿、品牌守卫 0 命中。
- 兼容：契约仍为 1.0，生成能力为可选挂载；旧流程图与项目无需迁移。

## [1.6.0] - 2026-11-15 — 可视化节点工作台（M7：条件分支、循环、运行基线与产物快照）

- 控制流节点：新增 `condition`（`when` 表达式，走 true/false 分支）与 `loop`（`max_iterations` 1–10、`until` 表达式、body 单链）两类节点；新增 `true` / `false` / `body` / `done` 端口；图校验支持条件/循环语义（分支唯一出边、循环 body 白名单、禁止嵌套）。
- 运行期：`conditions.evaluate` 安全表达式求值（不使用 eval）；执行引擎按分支剪枝（未选分支下游标记 skipped）、循环按迭代展开（步骤记录 `iteration`，循环节点记录 `iterations`），`until` 为真时提前退出。
- 回归基线：`flow baseline set/show/clear`；`flow diff --baseline [--fail-on-regression] [--max-regressions N] [--max-delta-ms N]` 可在 CI 中作为回归闸门。
- 产物快照：`project snapshot / snapshots / artifacts-diff` 与 Web 预览面板「创建产物快照 / 产物差异」；快照只记录路径、sha256 与大小，不复制内容。
- 项目摘要缓存：`GET /api/projects/<name>/summary` 按 state/workflows/runs/artifacts 最新 mtime 签名缓存，`?refresh=1` 强制刷新。
- 测试：新增 15 项（条件 5、基线 2、产物 3、控制流 2、Web API 3），合计 262 项通过；doctor 8 项、本地 CI 全绿、品牌守卫 0 命中。
- 兼容：契约仍为 1.0，新增字段均为可选，旧流程图与项目无需迁移。

## [1.5.0] - 2026-11-15 — 可视化节点工作台（M6：状态锁、运行对比、项目预览）

- 写状态节点安全并行：新增 `packages/flow/locks.py`（项目级文件锁 `00_project/.locks/state.lock`，陈旧锁自动清理、超时抛 `LockError`）与事务日志 `00_project/history/transactions.jsonl`；`knowledge_search` / `style_apply` / `style_inject` / `artifact_register` 等写节点持锁执行并标记 `parallel_safe`，可在并行波次中安全运行；`NodeContext.run_id` 写入事务记录。
- 运行对比：新增 `packages/flow/compare.py`（`compare_runs` / `format_compare_text`），按节点对齐输出 same / status_changed / slower / faster / added / removed 与耗时差值、回归/改善统计；CLI `flow diff`、Web API `GET /api/runs/<id>/diff?other=`。
- 项目预览：Web API `GET /api/projects/<name>/summary`（已登记产物文件、流程图节点与边、运行数）；项目面板新增「预览」入口，展示产物清单与流程图 SVG 缩略图并可点击切图；CLI 新增 `project summary`。
- 其他：`flow-run` 契约 step 增可选 `attempts`；修复 CLI 新命令退出码常量（`EXIT_OK`）。
- 测试：新增 11 项（锁 5、运行对比 3、并行写锁集成 1、Web API 2），全量 247 项通过；CI 全绿、品牌守卫 0 命中。

## [1.4.0] - 2026-11-15 — 可视化节点工作台（M5：并行执行、节点级重试、项目管理面板）

### 新增

- 并行分支执行：`runner.py` 引入波次（wave）调度——按拓扑深度分批，波内节点全部标记 `parallel_safe` 且 `settings.parallel=true` 时用 `ThreadPoolExecutor` 并发执行，否则串行；有状态节点（start/stage/知识/风格/产物/导出/确认）保持串行，`state.json` 仍是唯一事实来源。
- 节点级重试：节点可选 `retries`（0–3）、settings 可选 `node_retries`；执行器异常按次数重试并记录 `attempts` 与「第 k 次尝试失败 / 重试耗尽」日志；`flow run --retries N` 可覆盖默认值。
- 项目管理面板：Web 顶栏「项目」抽屉展示跨项目阶段/版本/待门禁/产物/流程图/运行/更新时间统计，点击切换项目；CLI `project list --stats` 输出同源统计（artifacts/pending_gates/workflows/runs/last_run）。
- 契约：`flow-run` step 增可选 `attempts`；`flow-graph` settings 增 `parallel`/`node_retries`、node 增 `retries`；`flow-node-types` 增 `parallel_safe`；`check_content`/`end` 为首批并行安全节点。
- 测试：新增 7 项（graph 3 / runner 3 / CLI 1 / Web 断言），全量 236 项通过；CLI 与 Web 冒烟通过。

## [1.3.0] - 2026-11-15 — 可视化节点工作台（M4：运行回放与图导入导出）

### 新增

- 运行回放：`packages/flow/replay.py`（`build_replay` / `format_replay_text`）把运行记录整理为时间线，含每步耗时、输出、错误与状态变更，并给出总耗时/步骤合计/最慢节点/失败节点定位；CLI `flow replay --project --run [--json]`；Web API `GET /api/runs/<id>/replay`。
- 流程图导入导出：CLI `flow export [--file | --project + --graph] [--out]` 与 `flow import --project --file [--graph] [--force]`；Web API `POST /api/workflows/import`；导入前复用 `validate_graph`（非法图 Web 返回 422、CLI exit 1），导入后归一化 graph_id/project/name。
- WebUI：顶栏「导出 / 导入」按钮（Blob 下载、文件选择上传）；运行历史点击打开回放抽屉（每步耗时、失败节点高亮、点击跳转节点），历史条目内附「恢复」按钮；新增回放样式。
- 测试：新增 `tests/test_flow_replay.py`（回放 3 + CLI 导入导出 2）与 Web API 2 项（`/replay`、`/import`），全量 229 项通过。

### 变更

- `flow` 包导出 `build_replay`、`format_replay_text`；`flow-run` 契约无需变更（回放是运行记录的派生视图）。
- 文档：`docs/flow-workbench.md` 升 1.3.0（回放、导入导出、限制更新）；README、command-card、troubleshooting、architecture 同步；新增 `docs/release-notes-1.3.0.md`。
- 版本进入 `1.3.0`（契约仍为 `1.0`，无破坏性变更）。

## [1.2.0] - 2026-11-15 — 可视化节点工作台（M2 + M3）

### 新增

- 节点类型从 4 类扩展到 10 类：`knowledge_search`（只读知识检索 + 知识卡落盘）、`style_apply`、`style_inject`（批量注入 + 逐镜记录）、`artifact_register`、`check_content`、`export`，保留 `start` / `stage` / `confirm` / `end`。
- 端口兼容表扩展（project / state / artifact / log / text / card / confirmed / knowledge_card / style_card / injection / any），知识卡与风格卡可直接进入确认节点或阶段节点。
- 模板库 `content/flow-templates.json` 4 套：从零到成片、B 入口接力、知识增强、风格注入；新增契约 `flow-templates.schema.json` 与 `packages/flow/templates.py`（加载/校验/实例化）。
- 运行历史与失败恢复：`store.list_runs`、`runner.recover_run`（可选恢复 `state_snapshot_before` 快照并备份到 `history/`），CLI `flow runs` / `flow recover`，Web API `GET /api/runs`、`POST /api/runs/<id>/recover`。
- 批量运行：CLI `flow batch`、Web API `POST /api/runs/batch`（默认 dry-run）。
- 任意 DAG 与跳阶段：`settings.allow_skip_stages` 把前跳校验降为警告；图校验仍保证恰好一个 start、至少一个 end、无环、端口兼容。
- 前端增强：模板选择新建、撤销/重做（Ctrl+Z / Ctrl+Y，快照栈上限 60）、array/object 参数 JSON 编辑、运行历史面板、失败恢复按钮、批量预演；节点库与端口配色、运行状态可视化。
- 统一内容检查：`core_router/check.py` 抽出 `content_checks()`，CLI `check --content` 与 flow `check_content` 节点共用同一实现，删除 CLI 中的重复逻辑。

### CLI / Web API

- `flow new --template`、`flow templates`、`flow runs`、`flow recover`、`flow batch`；`doctor` 增加 flow 模板检查（10 个节点类型、4 个模板、4 份契约）。
- Web API 新增 `/api/templates`、`/api/runs`（历史列表）、`POST /api/runs/batch`、`POST /api/runs/<id>/recover`。

### 测试与验证

- 新增 18 项测试（templates 6 / nodes 6 / runner 2 / Web API 4），全量 222 项通过；CLI 冒烟（模板实例化、dry-run、运行历史、批量预演、失败恢复 live 推进 01→02）通过；CI 全绿、品牌守卫 0 命中。
- 版本进入 `1.2.0`（契约仍为 v1.0，拓扑执行与 dry-run 语义不变）。

## [1.1.0] - 2026-11-15 — 可视化节点工作台（M1）

### 新增

- `packages/flow/`：图模型与校验（拓扑排序、端口兼容、8 条规则）、节点类型注册表、节点执行器、执行引擎（dry-run/确认断点/失败快照）、项目内存储（`00_project/workflows/`）。
- `packages/webui/`：Python 标准库 HTTP 服务 + 原生 JS/SVG 三栏画布（拖拽/连线/参数检查器/运行面板/确认抽屉），默认本机监听 + token。
- 3 份新契约（v0.1）：`flow-node-types`、`flow-graph`、`flow-run`；`content/flow-node-types.json`（start/stage/confirm/end 四类节点）。

### CLI

- 新增 `flow serve/new/list/show/validate/run`；`doctor` 增加 flow 检查（共 8 项）。

### 测试与验证

- 新增 34 项测试（flow 22 + Web API 12），全量 204 项通过；CLI 冒烟（dry-run + live 推进 01→02）通过；CI 全绿、品牌守卫 0 命中。
- 文档：`docs/flow-workbench.md`（架构、节点、数据结构、API、交互、限制、M2/M3）。

## [1.0.2] - 2026-11-15 — 工作台体验补丁

- 跨项目总览：`workbench.py project list`（缺省同时扫描文档目录默认项目根与仓库同级 `projects/`，可多次 `--root`；输出名称/阶段/版本/入口/风格/知识桥/更新时间，支持 `--json`，损坏项目跳过并提示）。
- 风格质量提示：`style list` 文本输出显示 A/B/C 分级数量、非 A 级条目的待核问题摘要；`style show` 增加「质量提示」行（等级 + 待核问题），JSON 输出保持原结构不变。
- 批量逐镜注入记录：`style inject-batch --per-shot-records` 在单份批量记录之外，为每条提示词写一份 `style-<id>-injection-<stage>-<tool>-<shot>.json`，便于逐镜追溯；`StyleService.inject_batch(..., per_shot_records=True)` 同步支持。
- `init` 输出补充：项目根目录、逐步下一步命令（check --content / gate / project list）与 `AI_FILM_PROJECTS_ROOT` 固定位置提示，减少项目分散摩擦。
- 新增 3 项测试（project list、init 提示、批量逐镜记录），全量 **170 项通过**；本地 CI 全绿、品牌守卫 0 命中。
- 文档：新增 `docs/release-notes-1.0.2.md`；README、command-card、troubleshooting、architecture、PRD 同步更新。
- 版本进入 `1.0.2`（契约仍为 v1.0，无破坏性变更）。

## [1.0.1] - 2026-11-15 — 真实项目补丁（P2 四项）

- 产物登记 CLI：`artifact register`（相对路径/glob/项目内绝对路径，自动 SHA-256 与字节数，写 `stage_artifacts` + `revision_log` + 刷新状态卡，路径去重）。
- 知识桥状态 CLI：`knowledge bridge --status off|requested|on`（可写 `last_card` 与 `confirmed_references`，不触发检索、不越过"知识桥不是阶段"的边界）。
- 跨阶段内容一致性检查：`check --content`（风格卡/知识卡存在性、`confirmed_references` ⊆ `state.references`、产物文件存在性、treatment 与 shot-plan 场次时长比对、acting 时长提示、`stale_downstream` 提示；错误退出码 1，仅提示退出码 0）。
- 风格批量注入：`StyleService.inject_batch` + CLI `style inject-batch`（整批结构校验、任一条失败整批拒绝、写一份 `style-<id>-injection-<stage>-<tool>-batch.json` 批量记录，可选 `--out-dir` 导出每条 txt）。
- 新增 18 项测试（`test_artifact.py` 8 / `test_content_check.py` 7 / style 批量 2 / 既有回归），全量 **167 项通过**；本地 CI 全绿、品牌守卫 0 命中。
- 文档：新增 `docs/release-notes-1.0.1.md`；README、command-card、troubleshooting、architecture、PRD 同步更新。
- 版本进入 `1.0.1`（契约仍为 v1.0，无破坏性变更）。

## [1.0.0] - 2026-11-14 — 迭代 4：试点与固化

- 参考记忆加载器 `core_router/memory.py`：阶段→范围映射（01-05 story、06 image、07 performance、08 camera），按 `status=enabled` 与 scope（含 `full`）自动加载；`reference list` CLI 命令。
- 项目导出/还原 `core_router.project.export_project / restore_project` + CLI `export` / `restore`：ZIP 内含 `export-metadata.json`；拒绝路径穿越与覆盖非空目标；还原后校验 state 并刷新状态卡。
- 试点驱动 `scripts/pilot_matrix.py`：试点 A（从零到 08，60 秒竖屏悬疑）与试点 B（B 入口接管到 05，作者剧本 SHA 不变）；迁移/规则升级、导出还原、品牌、漂移、门禁负向检查与 M1–M9 指标全部落盘 `docs/pilots/`。
- 试点 A 实测：01→02→04→05→06→07→08→done（v08），风格 001 希区柯克应用到 06/mj 与 08/seedance_2_0，05 修订后标记下游 06/07/08。
- 试点 B 实测：01→02→04→05（v04），05 自动加载 1 条参考方法，作者剧本 SHA-256 前后一致（未改稿）。
- 指标：M1 100%、M2 11/11、M3 100%（18/18，负向 4/4 拦截）、M4 平均 1.64 步/阶段、M5 100%、M6 100%、M7 0 命中（178 文件）、M8 0 漂移、M9 P0/P1=0；迁移与回滚演练（从 `history/upgrade-*` 还原 AGENTS.md 字节一致）、导出还原 19 文件一致。
- 文档定稿：`docs/command-card.md`、`docs/troubleshooting.md`、`docs/migration.md`、`docs/iteration-4-report.md`；README/architecture/PRD 同步。
- 新增 8 项测试（memory 4 / reference CLI 1 / 导出还原 3），全量 149 项通过；本地 CI 全绿；品牌守卫 0 命中；manifest 更新。
- 版本进入 `1.0.0`（契约仍为 v1.0）。

## [0.5.0] - 2026-11-14 — 迭代 3：C 风格服务

- 风格注册表 `scripts/build_style_registry.py` + `content/style-registry.json`：只读扫描 200 位导演风格包（10 类 × 20），生成编号/中英文名/分类/调色板（6 主色 + 4 情绪色 + 占比和）/`style_profile`/关键词/4 类模板行数/参考文件数/质量分级与问题清单；快照 **A 140、B 60、C 0**，重复主色调色板 0 组。
- 新增第 7 份契约 `packages/contracts/schemas/style-registry.schema.json`；构建报告 `docs/style-registry-report.md`（失效图链 59、目录名异常 8、manifest 旧绝对路径 79、缺来源说明 147）。
- 工具适配器 `packages/style_service/adapters.py`：8 工具结构契约 v1（06：mj/banana/sd；08：seedance_2_0/seedance_2_5/h3/runway/pika），`validate_prompt` 校验必填结构、必需/禁用标记、否定式、连续性禁令词、时长与运镜上限；`style_block` / `combined_prompt` 生成「【风格卡】七段 + 正文」。
- 风格服务 `registry.py` / `service.py`：按编号、中英文名、目录名解析注册表；`build_profile` 产出 `style-profile` 契约；`apply_profile` 写 `00_project/style-cards/style-<id>-profile.json` 并更新 `state.style`；`inject_prompt` 要求已 apply、按阶段限定工具白名单、只校验用户正文、写 `style-<id>-injection-<stage>-<tool>.json`（含正文 sha256 与组合提示词）。
- CLI 新增 `style list/show/resolve/validate/apply/inject`；`doctor` 增加风格注册表检查（共 7 项）；CLI 启动把 stdout/stderr 切到 UTF-8 容错（`errors="replace"`），提示词文件读取用 `utf-8-sig` 容忍 BOM。
- 新增 23 项测试（registry 4 / adapters 5 / service 9 / CLI 5），全量 141 项通过；本地 CI 全绿；品牌守卫 0 命中。
- Windows 实跑 E2E：真实项目 `悬疑短片PoC` → `style apply 001`（希区柯克）→ 06/mj 与 08/seedance_2_0 两次注入，记录与 `state.style` 一致。
- 文档：`docs/style-service.md`、`docs/iteration-3-report.md`；README/architecture/PRD 同步。

## [0.4.0] - 2026-11-14 — 迭代 1b：A 编排硬化

- 安装器 `packages/installer/`：`plan_install` / `install_skills`；同名旧 Skill 整体移入 `skills-backup-<时间戳>`，复制失败自动删除已装并恢复备份；升级时保留 `references/knowledge-base.json` / `knowledge-base.json` 原字节；支持 `--dry-run`。
- 初始化器 `core_router.project`：真实文档目录探测（Windows Shell 已知文件夹 / macOS 常见路径 / 环境变量覆盖），工作台配置（`~/.ai-film-workbench/config.json`），项目模板与状态卡 v2；`create_project` 生成 12 个项目目录、`state.json`、`brief.md`、`reference-memory.json`（`.md` 为人读视图）、`AGENTS.md`、`状态卡.md`。
- 状态卡 v2：`state.schema.json` 扩展知识桥、风格、确认文件、阶段产物、修订日志字段；`gates` 条目带阶段与更新时间。
- 门禁引擎 `core_router.gates`：注册表门禁 + 条件门禁（B 入口接管检查、知识桥开启后的知识卡确认）；硬门禁不可豁免；`advance` 在门禁未通过时拒绝并给出原因；上游修订按注册表顺序标记全部下游过期。
- 意图路由 `core_router.intent` + `content/intent-rules.json`：维护口令优先隔离（配置/更新知识库、整理新剧本、升级规则），其次知识库触发、修订、阶段、入口；修订优先于阶段识别。
- 参考记忆 v2：统一为 `00_project/reference-memory.json`（机器可读）+ `.md`（只读视图）；迁移器把旧「参考方法NNN」Markdown 条目转为契约条目，未知字段标注「迁移待核对」。
- 旧项目迁移 `migrate`：先备份到 `00_project/history/migrate-<时间戳>`，合并 brief/project-status/routing 字段为状态 v2，旧参考记忆改名为 `.legacy.md` 保留，写迁移报告，不改创作文件。
- 规则升级 `upgrade`：备份 `AGENTS.md` / `状态卡.md` / `routing.md` / `project-status.md`，补齐项目目录，按模板重写 `AGENTS.md`，刷新状态卡，写升级报告。
- CLI：新增 `route` / `gate`（list/pass/fail/waive）/ `next` / `install` / `migrate` / `upgrade`；`init` 改用初始化器，`doctor` 增加意图规则自检（共 6 项）；`check` 同时校验项目状态与参考记忆 JSON。
- 修正注册表 06→07 的默认推进关系（此前 06 会跳过 07）。
- 新增 50 项测试（gates 10 / intent 12 / project 12 / installer 7 / migrate 4 / E2E 5），全量 118 项通过；本地 CI 全绿。
- Windows 实跑 E2E：从零项目 01→02→04→05 推进（03 可选跳过）、门禁拦截、修订标记下游、旧项目迁移 + 规则升级。

## [0.3.1] - 2026-11-14 — 迭代 2.1：B 知识接入精度修订

- 证据质量评分：有效命中词数 + 结构语境词（情节/结局/身份/伏笔/结构/第三幕…）+2 + 常见叙事搭配（反转设计/身份反转/结局反转/核心事件…）+4 + 多词共现 +3；知识卡证据按评分降序（契约仍为 4 字段）。
- 动作/物件误命中过滤：「反转身」「反转过来」「反转过去」「反转方向」等模式内的命中不计入证据，并计入 `report.evidence_quality.filtered_mis_hits`。
- 置信策略：高置信证据（≥3 分）不少于 2 条时，丢弃纯字面低置信证据（计入 `low_confidence_dropped`）。
- 候选列表按证据最高分重排；报告新增 `evidence_quality`（considered/filtered_mis_hits/phrase_hits/cooccurrence_hits/top_score/high_confidence_evidence/low_confidence_dropped/sorted_by）。
- 新增 5 项测试，合计 68 项；覆盖质量排序、动作误命中过滤、短语/共现加权、低置信丢弃。
- 真实库实测（同查询）：8 条含噪声证据 → 2 条高置信证据（「身份反转设计」「核心事件：商战反转」），过滤动作误命中 3 条、丢弃低置信 3 条；知识库 SHA-256 与 mtime 不变。
- 更新文档：`docs/knowledge-service.md`（2.5 证据质量）、`docs/iteration-2-recall-report.md`（§8 精度修订实测）、`README.md`、`docs/architecture.md`。

## [0.3.0] - 2026-11-14 — 迭代 2：B 知识接入召回改进（方案 A）

- 元数据候选召回不足时，新增「有限正文回退」：按 lane 分类白名单 + 路径排除，在预算内逐份扫描 Markdown/TXT 正文并形成行级证据。
- 预算可配：`fallback_max_files`（默认 200）、`fallback_max_bytes`（单文件默认 256KB）；触发条件为证据不足或某个 lane 无候选；可用 `--no-fallback` 关闭。
- CLI 新增 `--no-fallback` / `--fallback-files` / `--fallback-bytes`；报告新增 `fallback`、`lane_candidates` 字段与文本输出行。
- 新增 4 项测试（adapter 1 + service 3），合计 63 项；覆盖预算上限、关闭开关、元数据未命中时的回退发现、lane/隔离边界。
- 真实库实测：仅 screenplay lane（元数据候选 0）→ 回退扫描 199 份，形成 8 条行级证据（05 剧本正文），知识库 SHA-256 与 mtime 不变；单次检索约 1 秒。
- 已知局限：回退为字面子串匹配，存在「反转身」等误命中；精度改进（多词共现/短语打分/词边界）留后续迭代。
- 新增文档：`docs/iteration-2-recall-report.md`；更新 `docs/knowledge-service.md`、`docs/architecture.md`。

## [0.2.0] - 2026-11-14 — 迭代 1a：B 知识服务 PoC

- 新增 `packages/knowledge_service/`：只读索引适配（`aistudio-md-2`）、行级证据链、知识卡组装与自校验。
- 新增 CLI：`knowledge probe` / `knowledge search`（知识卡写盘并可独立 `validate`）。
- 新增契约落地：知识卡（`knowledge-card` v1.0）在真实库实跑中通过 schema 校验。
- 新增 17 项测试（adapter 10 + service 7），覆盖只读、越界、无命中不编造、阶段→范围映射、CLI 退出码。
- 真实库验证：12,592 documents / 1,975 已索引正文；检索命中 4 条行级证据；检索前后知识库 SHA-256 与 mtime 不变。
- 新增文档：`docs/knowledge-service.md`、`docs/knowledge-poc-report.md`。
- 已知局限：现有 FTS5 表使用私有 tokenizer，外部不可复用；05/06 剧本召回率偏低，迭代 2 决策改进方案。

## [0.1.0] - 2026-11-14 — 迭代 0：地基

- 建立 `workbench` 开发仓库骨架与运行目录约定。
- 落地 contracts v1：`state` / `reference-memory` / `knowledge-card` / `style-profile` / `stage-artifact` / `stage-registry`。
- 落地 `stage-registry` v1（01–08 阶段 + 可选知识桥元数据，非阶段）。
- 落地 `brand-guard` v1：编码词表、变体归一化、白名单、表格文件扫描、CI 阻断。
- 落地 CLI 骨架：`version` / `doctor` / `check` / `brand-guard` / `init` / `validate`。
- 落地测试套件与本地 CI（`scripts/run_ci.py`）及 GitHub Actions 模板。
- 品牌基线：控制层与知识库说明文件零残留，语料人物名按例外保留。

## [0.0.1] - 2026-11-14

- 开发 PRD v0.1 评审草案。
