# 可视化节点工作台（M1–M16 + 2.0.1 实时预览 + M20 快照回滚 + M28 队列运维）

> 版本：2.27.0 · 状态：M1–M16 + 2.0.1 实时预览 + M20 Web 快照回滚面板 + M22 索引证据卡接入 + M28 队列运维增强 + M31/M32/M33/M34 队列告警、运维报表与批次报表 Web 化 + M35 批次报表 HTML 化 + M36 批次报表推送与告警静默窗口状态 + M38 实操上线引导 + M40 Web 操作台已完成 · 适用范围：本地单用户

## 1. 定位

在既有 CLI 工作台之上增加一层**可视化节点编排**：把「入口 / 阶段 / 人工确认 / 结束」抽象为节点，
用连线表达执行顺序与数据流，在浏览器里搭建、配置、运行、观察状态。

核心原则：

- **内核不变**：契约、阶段注册表、门禁、知识服务、风格服务、品牌守卫全部复用，节点执行即调用同一套函数。
- **state 唯一事实来源**：流程图只记录「流程意图 + 布局 + 运行记录」，执行结果仍写 `00_project/state.json`。
- **默认安全**：默认 dry-run；只监听 `127.0.0.1`；默认启用访问令牌；写操作限于项目目录内。
- **零第三方依赖**：Web 服务用 Python 标准库，前端用原生 JS/SVG。

## 2. 快速开始

```bash
cd workbench
# 1) 启动本地可视化服务（会打印带 token 的 URL）
python workbench.py flow serve --project 死亡外科医生

# 2) 浏览器打开打印出的 http://127.0.0.1:8899/?token=...

# 3) 在页面：选择项目 → ＋新建流程图（start + end 骨架）
#    从左侧节点库拖入「阶段 / 人工确认」，从端口拖线连接，右侧检查器改参数
# 4) 勾选「预演」→ 运行 → 查看日志与节点状态；确认节点会暂停并弹出确认抽屉
# 5) 预演通过后取消勾选「预演」→ 运行（live）会真实推进 state 与门禁
```

命令行等价操作：

```bash
python workbench.py flow new --project 死亡外科医生 --name 我的流程
python workbench.py flow list --project 死亡外科医生
python workbench.py flow show --project 死亡外科医生 --graph flow-main
python workbench.py flow validate --project 死亡外科医生 --graph flow-main
python workbench.py flow run --project 死亡外科医生 --graph flow-main --dry-run
python workbench.py flow run --project 死亡外科医生 --graph flow-main --live --yes

# 运行回放（每步耗时、失败节点定位）
python workbench.py flow replay --project 死亡外科医生 --run <run_id>

# 流程图导入 / 导出（JSON 即契约）
python workbench.py flow export --project 死亡外科医生 --graph flow-main --out flow.json
python workbench.py flow import --project 死亡外科医生 --file flow.json --graph imported-flow
```

## 3. 架构

```
浏览器（原生 JS/SVG）
      │  HTTP + token
      ▼
packages/webui/server.py（stdlib ThreadingHTTPServer）
      │  调用
      ▼
packages/flow/            packages/cli/main.py
  graph.py   图模型/校验   │  flow 子命令
  registry.py 节点类型     │
  store.py   项目内持久化  │
  nodes.py   节点执行器    │
  runner.py  执行引擎      │
      │  调用现有服务层
      ▼
core_router（state/门禁/advance） · knowledge_service · style_service · contracts · brand_guard
```

## 4. 节点类型（17 类）

两类 M7 控制流节点（详见 §14）：

- `condition`：输入 state/artifact/text/card/log，输出 `true` / `false` 两支；参数 `when`（默认 `always`，支持 `state.stage`、`state.version`、`iteration` 的比较表达式）。
- `loop`：输入 state，输出 `body` / `done`；参数 `max_iterations`（1–10，默认 3）与 `until`（默认 `never`）；body 为单链（阶段/知识/风格/产物/检查/导出），运行期按迭代展开，步骤记录 `iteration`、循环节点记录 `iterations`。

三类 M8 复合/生成节点（详见 §15）：

- `knowledge_adopt`：输入 state/knowledge_card，输出 reference/log；读取已确认知识卡（`card` 参数或 state 最近卡），dry-run 只计划，live 时把证据逐条写入参考记忆（编号 `参考方法NNN`），同步 `state.references`、`knowledge_bridge.status=on` 与 `confirmed_references`；需 `confirmed.by` 非空，重复证据自动去重。
- `style_bind`：输入 style_card/state，输出 reference/log；把风格画像绑定为 `style_reference` 参考记忆（scope 默认 image_06/camera_08），已存在则跳过；可附 `style` 参数先执行风格应用。
- `generate`：输入 state/text，输出 generation/log；按 `provider`（mock/seedance_2_0/seedance_2_5/minimax_h3）调用生成适配层，默认 dry-run 只建任务记录，`live=true` 且环境变量 key 存在时真实提交；任务记录写 `00_project/generations/jobs/`。
- `generate_adopt`：输入 state/generation，输出 artifact/log；参数 `job_id` 或 `all=true`（`limit`）、`stage`（01–08，默认 05）、`kind`（默认 generation）、`note`，把成功任务结果回填为项目产物并登记 state；dry-run 只计划。
- `generate_refresh`：输入 state/generation，输出 generation/log；参数 `job_id` 或 `all=true`（`limit` 1–100，默认 20），显式查询/刷新平台任务状态并更新本地记录；dry-run 只计划。


| 类型 | 分类 | 输入端口 | 输出端口 | 关键参数 | 执行语义 |
|---|---|---|---|---|---|
| `start` | 入口 | — | `project` | `project`（必填）、`entry`（A–D）、`note` | 加载 state、校验项目存在；入口不一致仅记录日志 |
| `stage` | 阶段 | `state`、`artifact` | `artifact`、`log` | `stage`（01–08 必填）、`auto_gates`（默认 true）、`note` | 要求 `state.stage` 与节点阶段一致；`auto_gates` 时自动通过当前阶段 pending 门禁；仍有未过则失败；通过后 `advance` |
| `knowledge_search` | 知识 | `state` | `knowledge_card`、`log` | `stage`、`problem`、`queries`（必填）、`candidates_limit`(40)、`evidence_limit`(8)、`fallback`(true)、`kb_root`、`index`（M22，可空，本地索引目录） | 调用只读知识服务检索，写 `00_project/knowledge-cards/<stage>-candidates.json`；知识桥状态 off→requested 并更新最近知识卡 |
| `style_apply` | 风格 | `state` | `style_card`、`log` | `style`（必填）、`tool`（8 工具之一） | 生成风格卡并更新 `state.style` |
| `style_inject` | 风格 | `state`、`text` | `injection`、`log` | `stage`（06/08）、`tool`、`items[{shot,prompt}]`、`per_shot` | 批量结构校验并写注入记录（可选逐镜记录） |
| `artifact_register` | 工具 | `state` | `artifact`、`log` | `stage`（01–08/done）、`kind`、`paths[]` | 登记产物到 `state.stage_artifacts` 与修订日志 |
| `check_content` | 工具 | `state` | `log` | `fail_on_error`（默认 true） | 执行跨阶段内容一致性检查；有错误时失败（除非关闭） |
| `confirm` | 控制 | `artifact`、`knowledge_card`、`style_card`、`injection`、`text`、`card`、`log` | `confirmed` | `prompt`（必填）、`detail_path`、`note` | 运行暂停（`awaiting_confirm`），人工确认后继续；拒绝则 `canceled` |
| `export` | 输出 | `state` | `artifact`、`log` | `out`（可选） | 导出项目 ZIP 并返回路径 |
| `end` | 输出 | `any` | — | `note` | 流程结束标记，输出当前阶段与版本 |

端口兼容表（`flow.graph.PORT_COMPAT`）：

| 输出端口 | 可连接输入端口 |
|---|---|
| `project` | `project`、`state`、`text`、`card`、`log` |
| `state` | `state` |
| `artifact` | `artifact`、`state`、`text`、`card`、`log`、`any` |
| `log` / `text` / `card` | `log`、`text`、`card`、`any`（互连） |
| `confirmed` | `confirmed`、`artifact`、`log`、`any` |
| `knowledge_card` / `style_card` | 同类、`card`、`text`、`log`、`artifact`、`any` |
| `injection` | `injection`、`artifact`、`log`、`text`、`any` |
| `reference` | `reference`、`artifact`、`log`、`text`、`card`、`any` |
| `generation` | `generation`、`artifact`、`log`、`any` |
| `any` | `any` |

## 5. 数据结构

### 5.1 流程图（`00_project/workflows/<graph_id>.json`，契约 `flow-graph.schema.json` v0.1）

```json
{
  "contract_version": "0.1",
  "graph_id": "flow-main",
  "name": "从零到 05",
  "project": "死亡外科医生",
  "created_at": "2026-11-15T10:00:00+08:00",
  "updated_at": "2026-11-15T10:00:00+08:00",
  "nodes": [
    { "id": "start", "type": "start", "label": "开始", "position": { "x": 80, "y": 140 },
      "params": { "project": "死亡外科医生", "entry": "A" } },
    { "id": "stage-01", "type": "stage", "label": "阶段 01", "position": { "x": 360, "y": 140 },
      "params": { "stage": "01", "auto_gates": true } },
    { "id": "end", "type": "end", "label": "结束", "position": { "x": 720, "y": 140 }, "params": {} }
  ],
  "edges": [
    { "id": "e1", "from": { "node": "start", "port": "project" }, "to": { "node": "stage-01", "port": "state" } },
    { "id": "e2", "from": { "node": "stage-01", "port": "artifact" }, "to": { "node": "end", "port": "any" } }
  ],
  "settings": { "auto_advance": true, "allow_skip_stages": false, "dry_run_first": true }
}
```

### 5.2 运行记录（`00_project/workflows/runs/<run_id>.json`，契约 `flow-run.schema.json` v0.1）

必填：`contract_version`、`run_id`、`graph_id`、`project`、`status`（`running`/`awaiting_confirm`/`succeeded`/`failed`/`canceled`）、`mode`（`full`/`to_node`/`single`）、`started_at`、`steps`。
每个 step：`node_id`、`status`（`pending`/`running`/`succeeded`/`failed`/`skipped`/`waiting_confirmation`/`planned`），可选 `state_before`、`state_after`、`outputs`、`logs`、`error`。
另含 `confirmations`、`state_snapshot_before`、`summary`、`dry_run`、`target_node`、`finished_at`。

### 5.3 节点类型注册表（`content/flow-node-types.json`，契约 `flow-node-types.schema.json` v0.1）

字段：`type`、`label`、`category`、`description`、`ports{in[],out[]}`、`params_schema`（JSON Schema 子集）、`executor`、`constraints`。

## 6. 图校验规则

`flow validate` / 保存接口执行同一套规则（契约校验 + 语义）：

1. 必须且只能有一个 `start`；
2. 至少一个 `end`；
3. 非 `start` 节点必须有入边，`start` 不能有入边，`end` 不能有出边；
4. 有输出端口的节点必须有出边；
5. 连线引用的节点/端口必须存在，端口类型必须兼容；
6. 不允许成环；
7. 同一阶段最多一个 `stage` 节点；
8. 阶段倒置报错；前跳超过 1 个阶段报错（`settings.allow_skip_stages=true` 时降为提示，需显式允许）。

## 7. 运行语义

- 执行顺序：Kahn 拓扑排序（同层按 y、x、id 稳定排序）。
- 运行模式：`full`（整图）、`to_node`（目标及其祖先）、`single`（仅目标）。
- dry-run：节点执行器返回 `planned`，除运行记录外不写任何项目文件；`settings.dry_run_first=true` 时 CLI/Web 默认 dry-run。
- 确认断点：遇到 `confirm` 节点时状态置 `awaiting_confirm` 并持久化；调用 `resume(approved)` 后继续；`--yes` / `auto_confirm` 可无人值守。
- 失败：节点异常记录 `failed` + 错误文本；运行记录保留 `state_snapshot_before` 便于对账。
- 幂等性：每次运行独立记录；重复运行以 state 当前状态为准（阶段不一致会明确失败，不会静默跳阶段）。

## 8. Web API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/workbench?project=` | 工作台/项目信息 |
| GET | `/api/projects` | 项目总览（默认项目根 + 工作台同级 projects） |
| GET | `/api/node-types` | 节点类型注册表 |
| GET | `/api/workflows?project=` | 流程图列表 |
| GET | `/api/workflows/<graph_id>?project=` | 流程图详情 |
| PUT | `/api/workflows/<graph_id>?project=` | 保存流程图（返回校验错误时 HTTP 422） |
| POST | `/api/workflows/new` | 新建骨架图（`{project,name}`） |
| POST | `/api/workflows/validate` | 校验（`{graph}`） |
| POST | `/api/runs` | 运行（`{project,graph_id,mode,target_node,dry_run,auto_confirm}`） |
| POST | `/api/runs/<run_id>/confirm` | 确认/取消断点（`{approved,note}`） |
| GET | `/api/runs/<run_id>?project=` | 运行记录 |
| GET | `/api/generate/providers` | 生成平台 provider 列表（4 个，含 env key 状态） |
| POST | `/api/generate/plan` | 生成预检（provider/prompt_text\|prompt_path/model/shot） |
| POST | `/api/generate/jobs` | 创建生成任务（默认 dry-run，`live` 需 key） |
| GET | `/api/generate/jobs?limit=` | 生成任务列表 |
| GET | `/api/generate/jobs/<job_id>` | 生成任务详情 |
| POST | `/api/generate/jobs/<job_id>/refresh` | 查询平台状态并更新任务记录（body: project） |
| POST | `/api/generate/jobs/refresh` | 批量刷新 submitted 任务（body: project / limit） |
| POST | `/api/generate/jobs/<job_id>/retry` | 重试 failed/canceled 任务（body: project / live） |
| POST | `/api/generate/jobs/<job_id>/adopt` | 回填 succeeded 结果为项目产物（body: project / stage / kind / note） |
| POST | `/api/generate/jobs/adopt` | 批量回填全部 succeeded 任务（body: project / stage / kind / note / limit） |
| POST | `/api/workflows/batch` | 批量运行（批次记录；body: project / graph_ids / all / dry_run / auto_confirm / auto_retry / fail_fast / limit） |
| GET | `/api/batches?project=&limit=` | 批次列表（最近批次摘要） |
| GET | `/api/batches/<batch_id>?project=` | 批次详情（每图状态/尝试/耗时/错误） |
| POST | `/api/batches/<batch_id>/recover` | 重跑该批次中的失败图并把新尝试合并进原批次（M13） |
| POST | `/api/queue` | 加入批次队列（body: project / graph_ids / all / dry_run / auto_confirm / auto_retry / fail_fast / parallel / workers） |
| POST | `/api/queue/run` | 执行项目队列中的 pending 条目（body: project / limit） |
| GET | `/api/queue?project=&status=&limit=` | 队列条目列表（含批次 ID、结果与失败通知） |
| POST | `/api/queue/<queue_id>/cancel` | 取消待运行队列条目（body: project） |
| POST | `/api/queue/<queue_id>/move` | 重排队列条目（body: project / before / after / index） |
| POST | `/api/queue/<queue_id>/retry` | 重置失败条目为待运行（body: project；M16） |
| GET | `/api/queue/notifications?project=&limit=` | 失败通知外送日志（JSONL，最近在前；M16） |
| GET | `/api/dev/version` | 静态资源签名（`filename:size:mtime_ns` + `latest_mtime_ns`）；前端每 1.2s 轮询，变更后整页刷新（2.0.1） |
| GET | `/api/rollback/snapshots?project=` | 项目状态快照列表（M20） |
| POST | `/api/rollback/create` | 创建项目状态快照（body: project / label；M20） |
| POST | `/api/rollback/apply` | 回滚到快照（body: project / snapshot / dry_run；回滚前自动安全快照；M20） |
- 兼容别名：`POST /api/runs/batch` 与 `POST /api/workflows/batch` 等价（旧字段 `count`/`results`），前端已迁移到新端点。

鉴权：默认启用令牌，通过 `?token=` 或请求头 `X-Workbench-Token` 传递；静态页面不拦截（仅本机监听）。

## 9. 前端交互

- 快照与回滚（M20）：运行面板「创建快照」「快照列表」列出快照（ID/说明/时间/文件数/大小），可「回滚」或 dry-run 预演；回滚复用 `core_router.rollback`，回滚前自动安全快照。

- 三栏布局：左侧节点库（分类 + 拖拽）、中间 SVG 画布、右侧检查器 + 运行面板。
- 画布：拖拽节点移动、节点右侧输出端口拖到另一节点输入端口连线、单击连线删除、中键拖动画布、滚轮缩放、Delete 删除所选节点。
- 检查器：显示名称、按 `params_schema` 自动生成参数表单（枚举/布尔/数字/文本）、禁用/启用、删除。
- 运行面板：dry-run 开关、模式（整图/到节点/单节点）、自动确认、步骤状态列表；断点确认抽屉显示 `prompt` 与 `detail_path`。
- 自动布局：按 start → 阶段顺序 → confirm → end 排列为网格；保存快捷键 `Ctrl+S`。
- 数据流观察：节点状态按最近一次运行着色（succeeded/failed/waiting_confirmation/planned），运行日志面板逐节点输出。

## 10. 安全边界

- 只监听 `127.0.0.1`（可用 `--host` 显式覆盖，默认不建议）。
- 默认令牌校验 `/api/*`；`--no-token` 仅建议临时本机调试。
- 写操作限制：流程图存于项目 `00_project/workflows/`，运行记录存于 `runs/`；不提供任意文件读写 API。
- live 运行会真实推进 state/门禁，属于显式操作（默认 dry-run 兜底）。

## 11. 回放与图导入导出（M4）

运行回放由 `packages/flow/replay.py` 从运行记录派生，不额外写项目文件：

- 时间线：每步 `node_id` / 节点类型 / 状态 / 开始结束时间 / `duration_ms` / 输出 / 错误 / `state_before`→`state_after`；
- 汇总：`total_duration_ms`、`step_duration_ms`、最慢节点、失败节点与错误、`recovered_from`；
- 入口：CLI `flow replay --project --run [--json]`；Web API `GET /api/runs/<id>/replay`；前端运行历史点击条目打开回放抽屉。

图导入导出（JSON 文件即契约）：

- 导出：`flow export --project P --graph G [--out f.json]` 或 `flow export --file f.json`；输出为 `flow-graph` JSON。
- 导入：`flow import --project P --file f.json [--graph 新id] [--force]`；导入前复用 `validate_graph`（契约 + 语义），失败逐条报错且不落盘；成功后重写 `graph_id/project/name`。
- Web：`POST /api/workflows/import`（body 含 `project` 与 `graph`；非法图返回 422）。

## 12. 并行执行与节点级重试（M5）

- 波次调度：`runner._wave_order()` 按拓扑深度把执行顺序切成若干波；单节点波串行。
- 并行条件：`settings.parallel=true`、波内节点数 >1、且该波所有节点类型都带 `parallel_safe=true`。首版仅 `check_content` 与 `end` 标记并行安全——所有写 `state.json` 的节点保持串行，避免竞态。
- 重试：节点参数 `retries`（0–3）优先，其次 `settings.node_retries`；执行器抛出 `NodeError`/`FlowError`/未知异常时按次数重试，步骤记录 `attempts` 与失败日志；`flow run --retries N` 覆盖全局默认。
- 风险提示：对写状态的节点开启重试可能产生重复副作用（例如重复登记产物），默认 0；确认节点不会在并行波内执行。
- 项目管理面板：`GET /api/projects` 返回每个项目的 artifacts / pending_gates / workflows / runs / last_run 统计；Web 顶栏「项目」抽屉可跨项目对比并切换；CLI `project list --stats` 输出同源数据。

## 13. 状态锁、运行对比与项目预览（M6）

- 状态锁：所有写 `state.json` 的节点通过 `packages/flow/locks.py` 的项目级文件锁（`00_project/.locks/state.lock`）串行执行；锁持有超时（默认 15s）抛 `LockError`，超过 120s 的陈旧锁自动清理；每次写操作追加 `00_project/history/transactions.jsonl`（含 run_id / node_id / stage / mutations）。
- 并行安全：标记 `parallel_safe=true` 的写节点（知识检索、风格应用/注入、产物登记、内容检查、导出、end）现在可在同一并行波次内运行；锁保证状态更新不丢。
- 运行对比：`flow diff --project P --run A [--other-run B] [--json]` 或 Web API `GET /api/runs/<id>/diff?other=`；输出每节点状态变化、耗时差、回归/改善计数。
- 项目摘要与预览：`project summary --project P` 与 `GET /api/projects/<name>/summary` 汇总已登记产物文件、流程图节点/边与运行数；Web 项目面板「预览」展示产物列表与流程图 SVG 缩略图，点击缩略图直接切换项目并加载该图。

## 14. 控制流、运行基线与产物快照（M7）

- 条件分支：`condition` 节点求值 `when` 表达式（`always` / `never` / `state.stage == 0N|done` / `state.version >= vNN` / `iteration < N` 等），只走 true 或 false 一条出边；未选分支的下游节点在运行记录中标记 `skipped`，dry-run 同样剪枝。
- 循环：`loop` 节点把 body 单链按 `max_iterations` 展开执行，每轮结束求值 `until`，为真提前退出；每个 body 步骤记录 `iteration`，循环节点记录 `iterations`。不支持嵌套循环；`loop` 本身不可直接执行（由执行引擎展开）。
- 运行基线：`flow baseline set --project P --run R [--graph G]` 保存一次运行作为基线；`flow diff --baseline [--fail-on-regression] [--max-regressions N] [--max-delta-ms N]` 与基线对比，回归超阈值时退出码 1，可作为 CI 闸门；`flow baseline show/clear` 查看与清除。
- 产物快照：`project snapshot --project P [--label L]` 对 01_story…06_prompts 下的文件记录路径、sha256 与大小（不复制内容）；`project snapshots` / `project artifacts-diff [--base ID] [--target ID]` 查看与当前或两份快照的差异；Web 项目预览面板提供「创建产物快照」「产物差异」按钮与差异文本。
- 摘要缓存：`GET /api/projects/<name>/summary` 按 state/workflows/runs/artifacts 最新 mtime 签名缓存，`?refresh=1` 强制刷新；CLI `project summary` 不受缓存影响。

## 15. 复合节点与生成平台（M8）

- 复合节点：`knowledge_adopt` 把已确认知识卡的证据固化为参考记忆（编号 `参考方法NNN`，type 按来源路径映射 screenplay/method_book/other，page_hits 存页码，method 带 160 字摘要），同时更新 `state.references`、`knowledge_bridge.status=on`、`confirmed_references`；`style_bind` 把风格画像写为 `style_reference`（scope 默认 image_06/camera_08），重复运行自动去重。
- 生成适配层：`packages/generate/providers.py` 读取 `content/generate-providers.json`（契约校验），`plan()` 校验模型白名单/字数上限/时长估算并计算 prompt sha256；`submit()` 默认 dry-run 只写任务记录，`--live` 且 `base_url_env`/`env_key` 存在时用 urllib POST 提交；`jobs.py` 以 `generate-job.schema.json` 记录 `planned/dry_run/submitted/succeeded/failed` 状态，文件存 `00_project/generations/jobs/`。
- provider：`mock`（本地联调，永远 dry-run）、`seedance_2_0` / `seedance_2_5`（`SEEDANCE_API_KEY`）、`minimax_h3`（`MINIMAX_API_KEY`）；`generate providers` 显示 key 是否设置。
- CLI/Web：`generate providers/plan/submit/jobs/show`；Web API 见 §8；前端节点库含 15 类节点，`reference`/`generation` 端口可连线；doctor 新增 generate 检查。
- 安全：默认 dry-run；真实提交必须显式 `--live`（或 Web `live:true`）且 key 存在；任务记录只写项目目录内。

### M9：任务状态轮询与 Web 生成面板（1.8.0）

- 状态查询：CLI `generate refresh <job_id>` / `generate refresh --all`；Web API `POST /api/generate/jobs/<job_id>/refresh` 与 `POST /api/generate/jobs/refresh`；只有非 dry-run 且 `status=submitted` 的任务会请求平台，终态任务原样返回。
- 平台响应归一：`_http_status()` 按 `status_path` 把 `{job_id}` 替换为平台外部 ID（从任务 `response` 的 id/job_id/task_id 等字段取），GET 带 Bearer；常见 running/succeeded/failed 状态词归一为契约三态，无状态字段但有结果 URL 视为 succeeded；失败时把平台错误写入任务 `error`。
- Web 生成面板：顶栏「生成…」打开；展示 4 个 provider 的 env key 是否设置、任务表（状态着色 + dry-run 标记）、预检与提交（live 需确认）、单任务刷新与「刷新全部 submitted」。
- 轮询是显式动作而非后台定时器；批量刷新单任务失败不影响其他任务（返回 `ok=false` 与错误文本）。

### M10：结果回填、失败重试与任务详情抽屉（1.9.0）

- 结果回填：CLI `generate adopt <job_id> --stage 05` / Web API `POST /api/generate/jobs/<job_id>/adopt`；仅 succeeded 且未回填的任务可回填，在 `<阶段目录>/generations/shot-XX__<job_id>.json` 写结果凭证（任务快照 + result_url + adopted_at + note），再经 `register_artifacts` 登记 `state.stage_artifacts`，任务记录写入 `adopted`；重复回填被拒绝。
- 失败重试：CLI `generate retry <job_id>` / Web API `POST /api/generate/jobs/<job_id>/retry`；仅 failed/canceled 可重试，按原 provider/模型/提示词创建新任务并记录 `retried_from`；默认沿用原任务提交方式（dry-run 重试仍 dry-run，可用 `--live`/`--dry-run` 覆盖）。
- 任务详情抽屉：生成面板任务表每行「详情」打开抽屉，显示 provider/模型/状态/镜头/提示词/字数、重试来源、回填结果、错误信息与任务 JSON；failed 显示「重试」、succeeded 未回填显示「回填」、已回填显示结果产物路径。
- 契约：`generate-job` 增加可选 `retried_from`、`adopted`（向后兼容）。

### M11：批量回填、生成平台流程节点与生成面板筛选（1.10.0）

- 批量回填：`adopt_all()` 只处理 succeeded 且未回填任务；逐条 adopt 会互相覆盖 `state.stage_artifacts[stage]` 摘要，因此最后统一 `register_artifacts` 组合登记；CLI `generate adopt --all [--limit]`，Web API `POST /api/generate/jobs/adopt`，生成面板「回填全部已成功」。
- 流程节点：`generate_refresh`（查询状态）与 `generate_adopt`（回填结果）可在流程图里编排，节点类型 15→17；参数 `job_id` 或 `all=true`，dry-run 只计划。
### M12：批次编排、批量自动重试与批次历史（2.0.0）

- 批次引擎：`packages/flow/batch.py` 的 `run_batch()` 逐图运行（默认 dry-run、auto_confirm），批次记录落 `00_project/workflows/batches/<batch_id>.json`（契约 `flow-batch` v0.1：图级 `attempts`/`run_id`/`duration_ms`/`error` 与 summary 统计）。
- 自动重试：失败图按 `--auto-retry 0–3` 重跑（每次新 run_id，成功或进入 awaiting_confirm 即视为该图完成）；`--fail-fast` 首个失败即停，`--limit` 限制图数量。
- CLI：`flow batch`（JSON 改为 `{ok,project,batch}`，破坏性）与新增 `flow batches`、`flow batch-show`。
- Web：`POST /api/workflows/batch`、`GET /api/batches`、`GET /api/batches/<batch_id>`；`POST /api/runs/batch` 保留兼容别名；前端批量预演展示尝试与耗时。


### 2.0.1：实时预览与界面迭代（PATCH）

- 实时预览：`GET /api/dev/version` 返回内置静态资源签名，前端 `startLivePreview()` 每 1.2s 轮询；签名变化时状态栏提示并整页刷新。
- 界面迭代：节点按分类着色（分类圆点 + 同色徽标）、端口连接圆点、连线贝塞尔箭头；预览演示项目新增「17 类节点演示」图（17 节点/26 连线）。
- 边界：整页刷新会重置缩放/选中；仅跟踪 3 个静态资源；后端 Python 改动需重启 `serve`。

### M13：批次并行预演与失败图恢复（2.1.0）

- 并行预演：`run_batch(..., parallel=True, workers=1–8)` 用线程池并行执行多个图，仅支持 dry-run；live 运行强制串行（共享 state 并发写风险），`parallel` 与 `fail_fast` 互斥；批次记录新增 `parallel`/`workers` 字段。
- 失败恢复：`recover_batch(project, batch_id)` 重跑批次中失败图，把新尝试追加到原批次 `attempts`（编号连续）并重算 status/summary；CLI `flow batch-recover`、Web `POST /api/batches/<batch_id>/recover`、前端失败时显示「恢复失败图」按钮。
- 边界：恢复沿用原批次记录，不产生新批次；恢复按图整体重跑，不从中途断点继续。
### M14：批次队列化与失败通知（2.2.0）

- 队列文件：`00_project/workflows/queue.json`（`flow-queue` 契约 v0.1）；`enqueue()` 解析 `--graphs` / `--all` 图列表，去重并校验（并行仅 dry-run），条目状态 pending。
- 顺序执行：`run_queue()` 按 `created_at` 升序处理 pending 条目，逐条调用 `run_batch` 并把批次 ID、结果汇总（成功/失败/尝试/耗时）写回；失败条目写 `notification.failed_graphs` 与 `message`，异常捕获为 failed。
- CLI/Web/前端：`flow queue add/list/run`；`--all-projects` 扫描默认项目根下所有项目排队执行；Web API `POST /api/queue`、`POST /api/queue/run`、`GET /api/queue`；运行面板「加入队列」「运行队列」按钮与队列列表（失败行红色 + 通知）。
- 边界：队列串行执行、不做定时调度；条目不会自动重试（可配合批次的 `auto_retry`）；队列文件在项目目录内（不越界写）。


### M15：队列定时调度、取消/重排与后台守护（2.3.0）

- 定时执行：队列条目新增可选 `scheduled_at`（ISO 8601）与 `order`；`run_queue()` 只执行到期条目，summary 增加 `scheduled`/`canceled` 计数；`flow queue add --at` 入队即计划。
- 取消与重排：`cancel_entry()` 仅允许 pending 取消（写 `notification` 说明）；`move_entry()` 支持 `before`/`after`/`index` 三选一重排，pending `order` 重赋 0..n-1；CLI `flow queue cancel/move`。
- 后台守护：`flow queue daemon --interval 30 --limit 5 [--until-empty] [--all-projects]` 周期执行到期条目，Ctrl+C 退出；无 daemon 时仍需显式 `flow queue run`。
- CLI/Web/前端：queue add 支持 `--at`；Web API `POST /api/queue/<id>/cancel`、`POST /api/queue/<id>/move`；前端队列列表显示顺序/计划时间与上移/下移/取消按钮。
- 边界：定时基于本机时钟，daemon 需保持进程运行；不自动重试失败条目；契约新增可选字段（向后兼容）。

### M28：队列运维增强（2.15.0）

- **cron 定时守护**：`flow queue daemon --cron "*/5 * * * *"`（5 段：分 时 日 月 周；支持 `*`、`*/n`、`a-b`、列表）按分钟匹配触发，记录 last fired 防止同一分钟重复；非法表达式退出 2。
- **批次失败 webhook**：`flow batch --webhook-url <URL>` 在批次有失败图时外送 `{at,event:"batch.run",project,batch_id,status,message,failed_graphs,summary}`；失败不阻断批次，结果由返回的 `webhook` 字段记录；未配置为 no-op。
- **Web 批次历史面板**：运行面板下方展示最近 10 个批次（状态/成功失败/耗时），失败批次可「恢复失败图」（复用 `POST /api/batches/<id>/recover`）。

### M16：队列失败重试与通知外送（2.4.0）

- 失败重试：`flow-queue` 契约条目新增可选 `attempts`（已重试次数）；`retry_entry()` 仅允许 failed 条目重置为 pending（attempts+1、清理批次/结果/通知字段）；`run_queue(..., retry_failed=N)` 先把 `failed 且 attempts<N` 的条目重置再执行；CLI `flow queue retry`、`flow queue run --retry-failed N`、`flow queue daemon --retry-failed N`；Web `POST /api/queue/<id>/retry` 与前端失败行「重试」按钮。
- 通知外送：失败运行写 JSONL 通知日志 `00_project/workflows/queue-notifications.jsonl`（at/event/status/message/failed_graphs/ran）；`notify_cmd` 可选外部命令（`--notify-cmd`，消息作为最后参数，超时 10s、失败静默）；CLI `flow queue notifications` 查询最近通知；Web `GET /api/queue/notifications`。
- 守护日志：`flow queue daemon --log-file/--rotate-bytes`（默认 `00_project/workflows/daemon.log`，超阈值轮转为 `.1`），每轮记录执行/重试/通知摘要与退出原因。
- 边界：重试为有限手动/守护触发，不含指数退避；通知日志与守护日志均在项目内；默认行为不变，契约只增可选字段。

## 16. 已知限制

1. 图与 state 仍为单向（图 → state）；不支持从现有 state 自动反推流程图。
2. 阶段节点要求当前项目阶段与节点一致；跨阶段自由回退需显式编排并自行确认。
3. 断点确认会话存于服务内存，服务重启后需重新运行。
4. 回放依据运行记录时间戳：串行节点精确，并行执行仅为近似。
5. 图导入导出只含流程图本身，不含项目状态与创作产物（跨项目迁移请用 `export` / `restore`）。
6. 状态锁只对同一台机器的进程有效；跨机器并发写同一项目不在支持范围。
7. 运行对比按 `node_id` 对齐；图结构变化较大时会出现 added/removed 噪声。
8. 项目预览只读取已登记产物与 `00_project/workflows/` 下的图，不扫描未登记的目录。
9. 循环只支持单链 body 且不能嵌套；body 内节点不能直接作为运行目标。
10. 条件表达式只支持预定义比较形式，不支持任意函数/布尔表达式；运行对比按 node_id 对齐，图结构变化大时会出现 added/removed 噪声。
11. 生成平台状态查询只在显式刷新时进行（不后台轮询）；真实查询需要 `base_url_env`/`env_key` 与网络，mock 与 dry-run 任务没有平台状态可查。
12. 复合节点采纳知识卡时使用卡片 `confirmed.by` 作为确认人；知识卡未确认会直接失败（可用 require_confirmed=false 关闭）。
13. Web 生成面板不自动定时刷新；页面停留期间任务状态需手动点「刷新」或「刷新全部 submitted」。
14. 回填只登记结果凭证 JSON（含平台结果 URL），不下载/转存平台视频文件；文件体积与可用性由平台决定。

15. 批量回填只处理最近 `limit` 条已成功且未回填任务，失败任务不进入结果；回填仍只登记凭证 JSON，不下载平台视频。
16. 生成节点需要显式给出 `job_id` 或 `all=true`，不会自动轮询、自动重试或自动回填。
17. 批次记录只保存图级汇总与尝试记录，不保存每次重试的完整运行详情；图校验失败的尝试不会生成运行记录。
18. 自动重试是有限次数（0–3）的同步重跑，不含退避/排队等待；生成长任务请配合 generate 节点与显式状态刷新。
19. 实时预览基于整页刷新，刷新后缩放/选中状态会重置；仅跟踪 3 个内置静态资源，后端 Python 改动需重启 `serve`。
20. 批次并行仅支持 dry-run 预演；live 运行共享项目状态，必须串行。失败图恢复沿用原批次记录并追加尝试，不创建新批次。
21. 批次队列按项目本地顺序执行（不跨进程并发）；定时条目需 `flow queue daemon` 或显式 `flow queue run` 触发，daemon 停止后不会自动执行。
22. 队列定时与后台守护依赖本机时钟与常驻进程；daemon 不自动重启失败条目，也不跨机器同步。
23. 取消/重排只作用于 pending 条目；running/succeeded/failed/canceled 条目不可取消或移动。
24. 失败重试是手动/守护触发的有限次重跑（按 `attempts` 上限），不含指数退避或跨机器队列。
25. 通知外送为尽力而为：JSONL 写入失败或外部命令超时/不存在时静默跳过，不阻断队列执行。
26. daemon 日志轮转只保留一份 `.1` 备份；日志文件在项目 `00_project/workflows/` 内。
27. 快照回滚为整文件覆盖（state/参考记忆/状态卡/流程图），不做内容级合并；回滚前自动创建安全快照，Web 面板需手动刷新。
28. webhook 重试为固定退避（1s/2s/3s），不含熔断/去重；飞书格式为纯文本消息（不含富文本/卡片/签名校验）。
29. 批次趋势报表为只读汇总（最近 N 批），不含图表渲染、跨项目聚合或定时生成。

## 17. 验证
- M33（2.20.0）新增 12 项测试（通知格式/重试 7、报表 4、CLI 集成 1），全量 `Ran 509 tests ... OK`；CLI 冒烟：`flow batch-report --format md --out`、`flow queue alerts --webhook-format feishu --webhook-retries 1`。
- M34（2.21.0）新增 3 项测试（告警去重 2：静默窗口抑制/不同失败图重发；Web API 1：`/api/batches/report` md/csv），全量 `Ran 512 tests ... OK`；Web 冒烟：批次面板「报表 MD/CSV/预览」；`flow queue alerts --dedupe-minutes` 二次推送返回 `suppressed=true`。
- M35（2.22.0）新增 1 项测试（HTML 报表：doctype/style/汇总卡片/趋势条/明细表/转义/无外链），全量 `Ran 513 tests ... OK`；CLI 冒烟：`flow batch-report --format html --out report.html`；Web 冒烟：批次面板「报表 HTML」下载与 `GET /api/batches/report?format=html`。
- M36（2.23.0）新增 5 项测试（报表推送事件/空 URL/未知格式、告警 state 展示、Web 推送端点），全量 `Ran 518 tests ... OK`；CLI 冒烟：`flow batch-report --push --webhook-url http://127.0.0.1:9/hook --json` 返回 `webhook.ok=false` 但批次报表正常生成；Web 冒烟：`POST /api/batches/report/push` 与告警面板静默窗口展示。
- M37（2.24.0）：新增 1 项测试（趋势 SVG 生成/Web 端点/CLI/飞书卡片共 6 项，全量 524 项）；`flow batch-trend --out` 导出自包含 SVG、`GET /api/batches/trend`、Web「趋势 SVG」按钮、`--webhook-format feishu_card`。
- M40（2.27.0）：新增 1 项测试（操作台端点：列表含 17 项与 danger、`project_list` 执行、缺参/未知 op 400），全量 `Ran 538 tests ... OK`；Web 冒烟：操作台打开 → 选择开工/项目/索引操作 → 执行并显示退出码与输出。

- 新增 22 项 flow 测试（图校验 12、执行引擎 10）+ 12 项 Web API 测试（M1）；M2/M3 新增 18 项（模板 6、能力节点 6、runner 2、Web API 4）。
- 全量 `Ran 222 tests ... OK`；CLI 冒烟：模板实例化、dry-run、运行历史、批量预演、失败恢复（live 恢复后 01→02）；`doctor` 8 项含 flow 模板检查。
- M4（1.3.0）新增 5 项回放/导入导出测试 + 2 项 Web API，全量 `Ran 229 tests ... OK`；CLI 冒烟：模板图 → dry-run → replay → export → import → 非法导入被拒。
- M6（1.5.0）新增 11 项测试（状态锁 5、运行对比 3、并行写锁集成 1、Web API 2），全量 `Ran 247 tests ... OK`；CLI 冒烟：两次 dry-run → `project summary` → `flow diff` → `project list --stats` → `doctor` / `flow validate` 通过。
- M7（1.6.0）新增 15 项测试（条件 5、基线 2、产物 3、控制流 2、Web API 3），全量 `Ran 262 tests ... OK`；CLI 冒烟：条件剪枝、循环展开、基线回归退出码、产物快照差异。
- M8（1.7.0）新增 21 项测试（generate 10、复合节点 8、Web API 3），全量 `Ran 283 tests ... OK`；CLI 冒烟：providers / plan / submit mock（job 记录）/ jobs / show；Web API dry-run 提交与任务查询；doctor 9 项全 OK。
- M9（1.8.0）新增 11 项测试（状态查询 9：dry-run 拒绝、终态短路、running/succeeded/failed 归一、批量容错、_http_status URL/Bearer/缺 env；Web API 2：单任务刷新、批量刷新），全量 `Ran 294 tests ... OK`；CLI 冒烟：providers / plan / submit mock / jobs / show / refresh --all；Web 生成面板冒烟（provider 表、任务表、预检、提交、刷新）。
- M10（1.9.0）新增 12 项测试（重试/回填 10：retry 状态校验与 retried_from、live 覆盖、缺提示词、adopt 状态校验/凭证与 state 登记/重复拒绝/无结果 URL、result_url 提取、未知阶段；Web API 2：重试端点、回填端点），全量 `Ran 316 tests ... OK`；CLI 冒烟：retry / adopt；Web 冒烟：任务详情抽屉、重试与回填按钮。
- M11（1.10.0）新增 10 项测试（批量回填 3、生成节点 6、批量回填 Web API 1），全量 `Ran 316 tests ... OK`；CLI 冒烟：`generate adopt --all`、`flow validate`（17 类）；Web 冒烟：生成面板状态筛选与「回填全部已成功」。
- 本地 CI `scripts/run_ci.py`：compile / tests / doctor / brand-guard 全 PASS；品牌守卫 0 命中。
- M12（2.0.0）新增 7 项测试（批次引擎 6：dry-run 批次记录/自动重试/fail_fast/limit/awaiting_confirm/非法批次；Web API 1：批次运行与历史查询），全量 `Ran 323 tests ... OK`；CLI 冒烟：`flow batch --all --dry-run`、`flow batches`、`flow batch --live --auto-retry 1`、`flow batch-show`；doctor 9 项含 5 份 flow 契约。
- 2.0.1 新增 2 项测试（dev 版本端点、静态文件变更后签名变化），全量 `Ran 325 tests ... OK`；手动验证：`serve` 后修改 `style.css`，约 1–2s 页面自动刷新（服务端日志可 `GET /api/dev/version` 轮询）。
- M13（2.1.0）新增 6 项测试（批次并行 dry-run、并行拒绝 live/fail-fast、恢复合并尝试、无失败恢复、Web API 并行端点/恢复端点），全量 `Ran 331 tests ... OK`；CLI 冒烟：`flow batch --parallel --workers 2`、`flow batch-recover`（失败图重跑并合并尝试）；doctor 9 项含 5 份 flow 契约。
- M14（2.2.0）新增 10 项测试（队列引擎 8：入队/过滤/去重/空选择/并行校验/顺序执行/失败通知/limit 与空队列；Web API 2：队列端点、失败通知），全量 `Ran 341 tests ... OK`；CLI 冒烟：`flow queue add/list/run`（含 `--all-projects`）；doctor 9 项含 6 份 flow 契约。
- M15（2.3.0）新增 10 项测试（定时跳过/计划执行、取消、重排 before/after/index、非法参数；Web API 2：定时+取消、重排），全量 `Ran 351 tests ... OK`；CLI 冒烟：`queue add --at`/`cancel`/`move`/`daemon --until-empty`；doctor 9 项含 6 份 flow 契约。
- M16（2.4.0）新增 8 项测试（队列重试/通知 6：重试重置、非 failed 拒绝、retry_failed 上限、通知日志、notify-cmd、无失败不通知；Web API 2：重试+通知、retry_failed），全量 `Ran 359 tests ... OK`；CLI 冒烟：`queue retry`、`run --retry-failed 1`、`queue notifications`、daemon 日志参数；doctor 9 项含 6 份 flow 契约。
- M28（2.15.0）新增 11 项测试（cron 8：通配/步长/范围/非法/周映射/日或周/字段/next_run；批次 webhook 3：成功外送、失败容错、未配置 no-op），全量 `Ran 470 tests ... OK`；CLI 冒烟：非法 `--cron` 退出 2 且提示 5 段格式、`flow batch --webhook-url` 输出 `webhook` 结果（连接失败不影响批次）。
- M20（2.8.0）新增 5 项测试（覆盖率 2、可复现构建 2、Web 回滚 1），全量 `Ran 387 tests ... OK`；CI 九步全 PASS（覆盖率 76.37%、repro PASS、品牌守卫 0 命中）；Web 冒烟：快照创建 → 列表 → dry-run → 回滚。
- M22（2.10.0）新增 12 项测试（索引证据卡服务 8、CLI 2、flow 节点 2），全量 `Ran 413 tests ... OK`；CLI 冒烟：`knowledge search --index` 生成同契约知识卡；flow `knowledge_search` 节点 `index` 参数运行后写 `00_project/knowledge-cards/<stage>-candidates.json`；索引缺失/无命中分别报可读错误与 `no_evidence`。

## 18. 后续（M41 候选）

- 操作台扩展：覆盖更多 CLI 操作、参数联动与批量任务队列（M41 候选）。
- 分支覆盖率从 51% 提升至 55%（补 webui/ops、queue、batch 分支）。
- 远端 CI 矩阵稳定性与 macOS 可选矩阵（需可用的托管 runner）。
- 创作主线试点 D：用工作台完成一个完整 60 秒短片的端到端生产。
