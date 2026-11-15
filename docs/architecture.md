# 架构说明

## 1. 目标

在保留现有 Skill 创作能力的前提下，把「提示词工程」升级为**可执行工作台**：

1. **流程确定**：阶段、门禁、状态、回退都有机器可读定义，不依赖聊天记忆。
2. **数据可交接**：项目目录 + 契约文件可被另一个模型、另一个平台或另一个人接续。
3. **能力可组合**：知识服务与风格服务是可选挂载点，不影响主链。
4. **内容可维护**：单一事实来源（SSOT）、契约版本化、CI 防回归。

## 2. 分层

```text
+-------------------------------------------------------------+
|  CLI（packages/cli）                                        |
|  version | doctor | check | brand-guard | init | route      |
|  gate | next | install | migrate | upgrade | validate       |
|  knowledge probe/search | style list/show/resolve/validate/apply/inject |
+-----------------------------+-------------------------------+
                              |
+-----------------------------v-------------------------------+
|  路由核心（packages/core_router）                            |
|  注册表 / 意图路由 / 门禁引擎 / 项目与状态 / 迁移与升级      |
+-----------------------------+-------------------------------+
                              |
+-----------------------------v-------------------------------+
|  契约层（packages/contracts）                                |
|  10 份 JSON Schema + 标准库子集校验器                         |
+-----------------------------+-------------------------------+
                              |
+-----------------------------v-------------------------------+
|  数据（content/ + config/）                                  |
|  stage-registry.json / intent-rules.json /                   |
|  style-registry.json / brand-guard.json                      |
+-------------------------------------------------------------+
                              |
+-----------------------------v-------------------------------+
|  能力（packages/）                                           |
|  knowledge_service（1a/2/2.1）| style_service（迭代 3）      |
|  installer（1b）；memory（迭代 4）；export/restore（迭代 4）；1.0.1：artifact register / knowledge bridge / check --content / inject-batch |
|  flow（1.1.0 M1 / 1.2.0 M2+M3）：graph / registry / nodes / runner / store / templates；webui：本地服务 + 原生前端（画布/撤销/历史/批量） |
+-------------------------------------------------------------+
```

- **契约层不依赖其他包**，可单独被外部工具复用。
- **路由核心只依赖契约层**，不读文件系统以外的状态。
- **CLI 是薄壳**，负责参数、日志与退出码，业务逻辑都在包里。
- **可视化编排层（1.1.0 M1 / 1.2.0 M2+M3）**：`packages/flow`（图模型与校验、10 类节点注册表、执行引擎、模板、运行历史与恢复、项目内存储）+ `packages/webui`（标准库 HTTP 服务 + 原生 JS/SVG 画布，含撤销/重做、参数 JSON 编辑、运行历史与批量）；节点执行复用现有服务层，`state.json` 仍是唯一事实来源，详 `docs/flow-workbench.md`。
- **1.2.0（M2/M3）落地能力节点、模板库、运行历史/失败恢复、任意 DAG 与跳阶段、批量运行、撤销重做；** 知识服务已实现只读适配 + 有限正文回退 + 证据质量评分；安装器、初始化器、门禁与迁移器在迭代 1b 落地；风格服务在迭代 3 落地（注册表 + 风格卡 + 8 工具适配 + 06/08 注入记录）；迭代 4 增加参考记忆加载器、项目导出/还原与试点驱动。**

## 3. 阶段模型

注册表 `content/stage-registry.json` 定义 8 个阶段：

| 阶段 | 名称 | Skill | 主产物 | 关键门禁 |
|---|---|---|---|---|
| 01 | 概念锚定 | film-synopsis | `01_story/synopsis.md` | 定位菜单、子选项确认 |
| 02 | 角色圣经 | film-characters | `01_story/characters.md` | 上游已确认 |
| 03 | 世界观（可选） | film-worldbuilding | `01_story/worldbuilding.md` | 上游已确认 |
| 04 | 分场大纲 | film-treatment | `01_story/treatment.md` | 时长预算 |
| 05 | 剧本深度融合 | film-screenplay | `02_script/screenplay.md` | 上游整合、场次锁定 |
| 06 | 图像资产 | film-lira-assets | `03_assets/assets-v01.md` | 生产资料、风格卡确认 |
| 07 | 表演 | film-acting | `04_performance/acting-v01.md` | 上游已确认 |
| 08 | 视频提示词 | film-cinedance | `05_shots/shot-plan-v01.md`、`05_shots/continuity-ledger-v01.md`、`06_prompts/seedance-v01.md` | 镜头规划门、模型选择 |

每个阶段声明：`inputs`、`outputs`、`gates`、`knowledge_mount`、`style_mount`、`model_options`、`state_fields`、`downstream`。

- `downstream` 用于推导下一阶段与标记「可能过期的下游」；08 没有下游。默认推进取 `downstream[0]`，因此 02 → 04（03 世界观可选跳过）；06 → 07（表演不可跳过）。
- 门禁分 `hard`（必须通过，不可豁免）与 `soft`（建议确认，可豁免）。
- 条件门禁：入口 B 在阶段 01 追加 `screenplay_intake`；知识桥状态非 `off` 时阶段 05 追加 `knowledge_card_confirm`；06 的 `style_card_confirm` 为 soft。
- 06 与 08 的 `style_mount` 为显式启用；其余阶段关闭。

知识桥是**元数据**而不是阶段：

```json
"knowledge_bridge": {
  "skill": "film-knowledge-bridge",
  "is_stage": false,
  "default": "off",
  "trigger_commands": [...],
  "maintenance_commands": [...]
}
```

这从结构上保证「知识桥不是第 09 阶段」，也保证它不会被错误计入阶段推进。

## 4. 数据流

```text
用户口令
  -> 意图路由（route）：维护口令优先隔离，其次知识库触发/修订/直接入口/阶段
  -> CLI 读取 00_project/state.json（入口/模式/阶段/版本/门禁/修订日志）
  -> 门禁检查：当前阶段 required gates 未全部 passed 时拒绝推进
  -> 读取 00_project/reference-memory.json（只加载启用的参考编号；`reference list` 可查）
  -> 若阶段为 06/08 且 state.style.status == on：读取风格卡，作为提示词前缀注入并写记录
  -> 执行当前阶段（注册表给出输入/输出/门禁）
  -> 产物写入阶段目录（vNN 版本），登记 state.stage_artifacts
  -> state.json 更新：阶段、版本、门禁、参考编号、可能过期下游
  -> 展示 + 落盘 + 等待确认
  -> next：门禁通过后推进到下一阶段
  -> 交付备份：export（ZIP + export-metadata.json）→ 需要时 restore
```

关键约束：

1. **state.json 是运行时唯一事实来源**；`状态卡.md` 与参考记忆 `.md` 是给人看的视图。
2. **未确认不得进入下游**；门禁状态驱动推进，硬门禁不可豁免。
3. **知识卡未确认不得交给创作阶段**；确认后才写参考记忆并分配 `参考方法NNN`。
4. **权威顺序固定**：用户本轮要求 > 最新已确认项目文件 > 启用参考方法 > 模型通用知识。
5. **上游修订**：`mark_downstream_stale` 按注册表顺序标记当前阶段之后的全部阶段为「可能过期」，不删产物。

## 5. 加载顺序

1. `python workbench.py` 启动，读取仓库内 `VERSION`、`content/stage-registry.json`、`content/intent-rules.json`。
2. 校验注册表（结构 + 引用完整性）与意图规则；失败则拒绝创建项目。
3. 口令先过意图路由：维护口令直接转交知识服务/升级流程，不进入创作；创作口令映射到入口/阶段/修订。
4. `init`：探测文档目录（可由 `AI_FILM_DOCUMENTS_DIR` 覆盖），按目录约定创建项目，写入 `state.json`（经 `state.schema.json` v2 校验）、`AGENTS.md`、状态卡、参考记忆 JSON/MD。
5. 阶段执行时：`gate list` 查门禁 → 执行阶段 → `gate pass` 记录确认 → `next` 推进（未过门禁退出码 1）。
6. 每次提交：CI 依次跑编译、测试、doctor、brand-guard。

## 6. 与现有 Skill 子系统的映射

| 现有资产 | 工作台对应 |
|---|---|
| ai-film-router（阶段路由） | `stage-registry.json` + `core_router`（intent 意图路由 + gates 门禁引擎） |
| 项目级 AGENTS.md / routing.md / project-status.md | `00_project/state.json`（v2）+ 生成的 AGENTS.md + 状态卡视图；旧文件由 `migrate` 合并 |
| reference-memory.md / 00-本地知识库参考记忆.md | `00_project/reference-memory.json`（结构化，契约校验）+ `.md` 只读视图；旧命名由 `migrate` 识别 |
| film-knowledge-bridge + 检索脚本 | `knowledge_service`（1a PoC + 迭代 2 方案 A + 2.1 精度修订：只读适配 + 有限正文回退 + 证据质量评分 + 行级证据链，不重建索引） |
| 200 位导演色卡（SKILL200） | `style_service`（迭代 3：`content/style-registry.json` + 风格画像契约 + 8 工具结构校验 + 06/08 注入记录，只读引用外部风格包） |
| 安装/升级脚本 | `installer`（迭代 1b：备份/幂等/回滚/配置保留）+ `migrate` / `upgrade` |
| 意图口令（中文口令卡、维护口令） | `content/intent-rules.json` + `core_router.intent` |
| 品牌清理 | `brand_guard` + CI |
| 项目备份/移交（手动拷目录） | `core_router.project.export_project` / `restore_project` + CLI `export` / `restore`（ZIP + 元数据 + 路径穿越校验） |
| 跨阶段参考记忆读取 | `core_router.memory`（阶段→scope 映射、启用条目自动加载）+ CLI `reference list` |
| 阶段产物登记（原手动改 state） | 1.0.1：`core_router.project.register_artifacts` + CLI `artifact register`（SHA-256/字节数/修订日志/刷新状态卡/路径去重） |
| 风格批量注入（原逐条覆盖） | 1.0.1：`StyleService.inject_batch` + CLI `style inject-batch`（整批校验、失败整批拒绝、单份批量记录） |
| 可视化节点编排 | 1.1.0（M1）+1.2.0（M2/M3）+1.3.0（M4）+1.4.0（M5）+1.5.0（M6）+1.6.0（M7）+1.7.0（M8）+1.8.0（M9）+1.9.0（M10）：`packages/flow`（15 类节点/模板/历史/恢复/控制流）+ `packages/generate`（4 provider/任务记录/状态轮询/结果回填/失败重试）+ `packages/webui`（画布/撤销/批量/生成面板/任务详情抽屉）+ CLI `flow` / `generate` 子命令 |
| 项目一致性体检 | 1.0.1：`check --content`（风格卡/知识卡/产物存在性、confirmed⊆references、treatment↔shot-plan 时长、下游过期提示） |

迁移策略：**先适配、后重建**。迭代 1a 已用只读适配验证现有 `aistudio-md-2` 索引格式（详情见 `docs/knowledge-service.md`、`docs/knowledge-poc-report.md`），不改动知识库本体；契约层统一抽象，避免把现有脚本的私有格式带进新架构。迭代 2 方案 A（0.3.0）以有限正文回退补足预算内召回，迭代 2.1（0.3.1）加入证据质量评分与误命中过滤（见 `docs/iteration-2-recall-report.md`）；完整覆盖与语义级精度仍以方案 B（按契约重建索引）为中期路径。迭代 1b（0.4.0）把旧项目的规则文件合并进状态卡 v2，旧参考记忆转为契约 JSON 并保留 `.legacy.md` 原件（见 `docs/iteration-1b-report.md`）。迭代 3（0.5.0）只读扫描外部 200 位导演风格包生成 `content/style-registry.json`，风格素材不复制进仓库，风格卡与注入记录写入项目（见 `docs/iteration-3-report.md`）。迭代 4（1.0.0）用两个试点（从零到 08、B 入口到 05）验证全链路，补参考记忆加载器与导出/还原，并完成迁移升级与回滚演练（见 `docs/iteration-4-report.md`、`docs/migration.md`）。1.0.1 是真实项目试点（《死亡外科医生》从零到 done）后的补丁：新增产物登记与知识桥状态 CLI、跨阶段内容一致性检查、风格批量注入，不改变契约与阶段路由（见 `docs/release-notes-1.0.1.md`、`docs/pilot-c-report.md`）。1.0.2 为体验补丁：跨项目总览、风格质量提示、批量逐镜注入记录、init 下一步引导（见 `docs/release-notes-1.0.2.md`）。1.1.0 增加可视化节点工作台（M1）：新增 flow/webui 两层与 3 份 v0.1 契约，节点执行复用既有服务层，不改变 state v2 与阶段路由（见 `docs/flow-workbench.md`）。M8（1.7.0）新增复合节点（知识卡采纳、风格绑定）与生成平台适配层，生成任务记录落项目 `00_project/generations/jobs/`，默认 dry-run、零第三方依赖（见 `docs/release-notes-1.7.0.md`）。M9（1.8.0）为生成任务增加显式的平台状态查询/刷新（CLI 与 Web API）与 Web 生成面板，轮询作为显式动作、不后台自动进行；M10（1.9.0）增加生成结果回填（`adopt`）与失败重试（`retry`，`retried_from` 溯源）及 Web 任务详情抽屉（见 `docs/release-notes-1.8.0.md`、`docs/release-notes-1.9.0.md`）。

## 7. 错误码与退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 校验失败 / 命中禁用词 / 业务拒绝 |
| 2 | 参数或用法错误（argparse） |
| 3 | 环境不可用（doctor 失败、配置缺失、依赖异常） |

## 8. 版本与兼容

- 契约 `contract_version` 固定 `1.0`；破坏性变更必须升 `2.0` 并提供迁移脚本。
- 注册表与契约同版本发布；`manifest.json` 记录文件哈希，供安装器校验。
- `VERSION` 遵循 semver：迭代 0 为 `0.1.0`，迭代 1a（B 知识服务 PoC）为 `0.2.0`，迭代 2 方案 A（有限正文回退）为 `0.3.0`，迭代 2.1（精度修订）为 PATCH `0.3.1`，迭代 1b（A 编排硬化）为 `0.4.0`，迭代 3（C 风格服务）为 `0.5.0`，迭代 4（试点与固化）为 `1.0.0`，真实项目补丁为 PATCH `1.0.1`，体验补丁为 PATCH `1.0.2`；可视化节点工作台（M1）为 MINOR `1.1.0`。1.0.0 为功能完善后的首个正式版本；后续 breaking change 升 2.x，M4（运行回放与图导入导出）为 `1.3.0`，M5（并行执行、节点级重试、项目管理面板）为 `1.4.0`，M6（状态锁与事务、运行对比、项目预览）为 `1.5.0`。M7（条件分支/循环、运行基线与产物快照）为 1.6.0，M8（复合节点、生成平台适配层）为 1.7.0，M9（生成任务状态轮询、Web 生成面板）为 1.8.0，M10（生成结果回填、失败重试、任务详情抽屉）为 1.9.0。
- **M7（1.6.0）**：条件分支/循环节点与安全表达式求值、分支剪枝与循环展开；运行基线保存与回归阈值告警（CI 闸门）；项目摘要缓存与产物快照差异视图。
- **M8（1.7.0）**：复合节点 `knowledge_adopt` / `style_bind`（知识卡/风格卡确认后自动写参考记忆）；生成平台适配层 `packages/generate`（4 provider、任务记录、dry-run 默认、CLI/Web API）。
- **M9（1.8.0）**：生成任务显式状态查询/刷新（`refresh` / `refresh_all`，平台响应归一 running/succeeded/failed，终态短路、dry-run/mock 拒绝；CLI `generate refresh` 与 Web `POST /api/generate/jobs[/<id>]/refresh`）；Web 生成面板（provider env 状态、任务表状态着色、预检/提交/刷新）。
- **M10（1.9.0）**：生成结果回填（`adopt`：succeeded 结果写 `<阶段目录>/generations/` 凭证并登记 `state.stage_artifacts`，任务写 `adopted`）与失败重试（`retry`：failed/canceled 生成新任务并记录 `retried_from`）；CLI `generate adopt` / `generate retry` 与 Web 对应 API；生成面板任务详情抽屉。
- 旧项目的兼容策略：状态卡 v2 新字段全部可选，迁移前旧 `state.json` 仍可校验；规则文件通过 `migrate` / `upgrade` 升级，创作产物字节不动。

## 9. 可视化节点工作台（1.1.0 M1 / 1.2.0 M2+M3 / 1.3.0 M4 / 1.4.0 M5 / 1.5.0 M6 / 1.6.0 M7 / 1.7.0 M8 / 1.8.0 M9 / 1.9.0 M10）

- 新增 `packages/flow/`：`graph.py`（图模型、端口兼容、拓扑排序、图校验 8 条规则）、`registry.py`（节点类型注册表与参数校验）、`nodes.py`（start/stage/confirm/end 执行器）、`runner.py`（运行记录、dry-run、确认断点、失败快照）、`store.py`（项目内 `00_project/workflows/` 与 `runs/` 持久化）。
- 新增 `packages/webui/`：标准库 `ThreadingHTTPServer` + 原生 JS/SVG 前端；默认监听 `127.0.0.1` 且启用 token；API 覆盖工作台信息、项目、节点类型、流程图读写校验、运行与确认。
- 契约新增 3 份 v0.1：`flow-node-types.schema.json`、`flow-graph.schema.json`、`flow-run.schema.json`；`content/flow-node-types.json` 定义四类节点。
- CLI 新增 `flow serve/new/list/show/validate/run`；`doctor` 增加 flow 检查（8 项）。
- 边界：流程图只记录流程意图、布局与运行记录；`state.json` 仍为唯一事实来源；节点执行调用现有服务层（门禁/advance、知识、风格、产物登记等），无第二套业务逻辑。
- 验证：新增 34 项测试（22 flow + 12 Web API），全量 204 项通过；CI 全绿；文档 `docs/flow-workbench.md`。
- M2/M3（1.2.0）：新增 10 类节点（知识检索/风格 apply+inject/产物登记/内容检查/导出）、4 套模板、运行历史与失败恢复、任意 DAG/跳阶段、批量运行、撤销重做；对 `flow-run` 契约增加可选 `recovered_from`/`state_restored`；新增 18 项测试合计 222 项。
- M4（1.3.0）：`packages/flow/replay.py` 派生运行回放（耗时/最慢/失败节点定位），CLI `flow replay`、`flow export` / `flow import`，Web API `GET /api/runs/<id>/replay` 与 `POST /api/workflows/import`；前端运行历史打开回放抽屉并支持 JSON 导入导出；新增 7 项测试合计 229 项。
- M5（1.4.0）：`runner.py` 增加波次调度与节点级重试（step 记录 `attempts`；仅 `parallel_safe` 只读节点可并行，写状态节点串行）；`flow-graph` 增 `settings.parallel`/`settings.node_retries`/`node.retries`，`flow-node-types` 增 `parallel_safe`；`GET /api/projects` 与 `project list --stats` 提供跨项目统计；Web 顶栏新增项目面板。
- M6（1.5.0）：`packages/flow/locks.py` 提供项目级状态锁与事务日志；写状态节点（知识检索/风格/产物登记）持锁执行并标记并行安全；`packages/flow/compare.py` 提供两次运行对比（状态/耗时/回归）；`GET /api/projects/<name>/summary` 与 Web 项目面板「预览」提供产物清单与流程图缩略图。
- M7（1.6.0）：`conditions.py` 安全表达式求值与 `runner.py` 分支剪枝/循环展开；运行基线（`baselines.json`）与 `flow diff --baseline` 回归阈值；`artifacts.py` 产物快照与差异；项目摘要 mtime 缓存。
- M8（1.7.0）：`nodes.py` 增加 `knowledge_adopt` / `style_bind` / `generate` 三个执行器；新增 `packages/generate`（`providers.py` 注册表/计划/提交、`jobs.py` 任务记录、`generate-providers.schema.json` 与 `generate-job.schema.json`）；节点类型 15 类、端口 `reference`/`generation`；CLI `generate` 子命令与 Web `/api/generate/*`。
- M9（1.8.0）：`providers.py` 增加 `_http_status` / `refresh` / `refresh_all`（平台状态归一、终态短路、批量容错）；CLI `generate refresh`；Web API 单任务与批量刷新、`env_set` 字段；前端新增生成面板（provider/任务表/预检/提交/刷新）。
- M10（1.9.0）：`providers.py` 增加 `result_url` / `adopt` / `retry`（succeeded 结果写凭证并登记产物、failed/canceled 重试并记录 `retried_from`）；`generate-job` 契约新增可选 `retried_from`/`adopted`；CLI `generate adopt`/`generate retry`；Web API retry/adopt 与任务详情抽屉。
