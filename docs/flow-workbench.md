# 可视化节点工作台（M1 / M2 / M3 / M4 / M5 / M6 / M7）

> 版本：1.6.0 · 状态：M1–M7 已完成 · 适用范围：本地单用户

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

## 4. 节点类型（12 类）

两类 M7 控制流节点（详见 §14）：

- `condition`：输入 state/artifact/text/card/log，输出 `true` / `false` 两支；参数 `when`（默认 `always`，支持 `state.stage`、`state.version`、`iteration` 的比较表达式）。
- `loop`：输入 state，输出 `body` / `done`；参数 `max_iterations`（1–10，默认 3）与 `until`（默认 `never`）；body 为单链（阶段/知识/风格/产物/检查/导出），运行期按迭代展开，步骤记录 `iteration`、循环节点记录 `iterations`。


| 类型 | 分类 | 输入端口 | 输出端口 | 关键参数 | 执行语义 |
|---|---|---|---|---|---|
| `start` | 入口 | — | `project` | `project`（必填）、`entry`（A–D）、`note` | 加载 state、校验项目存在；入口不一致仅记录日志 |
| `stage` | 阶段 | `state`、`artifact` | `artifact`、`log` | `stage`（01–08 必填）、`auto_gates`（默认 true）、`note` | 要求 `state.stage` 与节点阶段一致；`auto_gates` 时自动通过当前阶段 pending 门禁；仍有未过则失败；通过后 `advance` |
| `knowledge_search` | 知识 | `state` | `knowledge_card`、`log` | `stage`、`problem`、`queries`（必填）、`candidates_limit`(40)、`evidence_limit`(8)、`fallback`(true)、`kb_root` | 调用只读知识服务检索，写 `00_project/knowledge-cards/<stage>-candidates.json`；知识桥状态 off→requested 并更新最近知识卡 |
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

鉴权：默认启用令牌，通过 `?token=` 或请求头 `X-Workbench-Token` 传递；静态页面不拦截（仅本机监听）。

## 9. 前端交互

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

## 15. 已知限制

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

## 16. 验证

- 新增 22 项 flow 测试（图校验 12、执行引擎 10）+ 12 项 Web API 测试（M1）；M2/M3 新增 18 项（模板 6、能力节点 6、runner 2、Web API 4）。
- 全量 `Ran 222 tests ... OK`；CLI 冒烟：模板实例化、dry-run、运行历史、批量预演、失败恢复（live 恢复后 01→02）；`doctor` 8 项含 flow 模板检查。
- M4（1.3.0）新增 5 项回放/导入导出测试 + 2 项 Web API，全量 `Ran 229 tests ... OK`；CLI 冒烟：模板图 → dry-run → replay → export → import → 非法导入被拒。
- M6（1.5.0）新增 11 项测试（状态锁 5、运行对比 3、并行写锁集成 1、Web API 2），全量 `Ran 247 tests ... OK`；CLI 冒烟：两次 dry-run → `project summary` → `flow diff` → `project list --stats` → `doctor` / `flow validate` 通过。
- M7（1.6.0）新增 15 项测试（条件 5、基线 2、产物 3、控制流 2、Web API 3），全量 `Ran 262 tests ... OK`；CLI 冒烟：条件剪枝、循环展开、基线回归退出码、产物快照差异。
- 本地 CI `scripts/run_ci.py`：compile / tests / doctor / brand-guard 全 PASS；品牌守卫 0 命中。

## 17. 后续（M8 候选）

- 复合节点（知识卡/风格卡确认后自动写入参考记忆）。
- 与真实生成平台 API 对接（Seedance / H3 等）。
- 运行基线的定时巡检与趋势图、缩略图文件缓存落盘。
- macOS / GitHub Actions 远端矩阵与迁移用例扩充。

