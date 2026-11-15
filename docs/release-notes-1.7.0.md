# workbench 1.7.0 发行说明（M8：复合节点与生成平台适配层）

- 版本：1.7.0（契约 1.0，新增 2 份 v0.1 子契约）
- 日期：2026-11-15
- 范围：可视化节点工作台 M8——复合节点与真实生成平台适配层

## 新增能力

### 复合节点

- `knowledge_adopt`：读取已确认知识卡（`card` 参数或 `state.knowledge_bridge.last_card`），把证据逐条写入参考记忆 `00_project/reference-memory.json`（编号 `参考方法NNN`），并同步 `state.references`、`knowledge_bridge.status=on`、`confirmed_references`。
  - 未确认（`confirmed.by` 为空）默认失败，可用 `require_confirmed=false` 关闭。
  - 去重键 `(local_path, page_hits)`，重复运行不重复写入。
  - type 映射：`05-` / `06-` / `07-` → `screenplay`，`08-` → `method_book`，其余 → `other`。
- `style_bind`：把风格画像绑定为 `style_reference` 参考记忆（`page_hits` 固定「色卡/风格画像」，`scope` 默认 `image_06` / `camera_08`），已存在则跳过；可给 `style` 参数先执行风格应用。

### 生成平台适配层（`packages/generate`）

- provider 注册表 `content/generate-providers.json`（契约 `generate-providers.schema.json`）：mock / seedance_2_0 / seedance_2_5 / minimax_h3。
- `plan()`：模型白名单、字数上限、时长估算、prompt sha256、dry-run 判定（mock 恒 dry-run；无 key 时 video 也 dry-run）。
- `submit()`：默认 dry-run 只写任务记录；`--live` 且 `base_url_env` / `env_key` 存在时用 urllib POST 提交，失败记录 failed 并抛错。
- `jobs.py`：任务记录 `00_project/generations/jobs/<job_id>.json`（契约 `generate-job.schema.json`），状态 `planned/dry_run/submitted/succeeded/failed`；`list_jobs` 按 created_at 倒序。

### 集成

- 节点类型 12→15（`knowledge_adopt` / `style_bind` / `generate`），新增 `reference` / `generation` 端口与 PORT_COMPAT 兼容。
- CLI：`generate providers/plan/submit/jobs/show`（均支持 `--json`）。
- Web API：`GET /api/generate/providers`、`POST /api/generate/plan`、`POST /api/generate/jobs`、`GET /api/generate/jobs[?limit=]`、`GET /api/generate/jobs/<job_id>`。
- 前端：节点库自动显示 15 类节点，`reference` / `generation` 端口可连线。
- doctor：新增 generate 检查（provider 加载、契约注册），共 9 项检查。

## 验证

- `Ran 283 tests ... OK`（新增 21 项：generate 适配层 10、复合节点 8、Web API 3）。
- CLI 冒烟：providers、plan（seedance_2_5）、submit（mock → dry_run 任务记录）、jobs、show。
- Web API 冒烟：providers、plan、jobs（dry-run 提交 + 查询）。
- 本地 CI 全绿、品牌守卫 0 命中；`doctor` 9 项全 OK。

## 安全与限制

- 默认 dry-run；真实提交必须显式 `--live`（Web `live:true`）且环境变量 key 存在。
- 不自动轮询平台状态；任务状态需人工用 job_id 查询。
- 任务记录只写项目目录内；生成能力为可选挂载，旧流程图与项目无需迁移。
