# workbench 1.10.0 发行说明（M11：批量回填、生成平台流程节点与生成面板筛选）

> 版本：1.10.0 · 日期：2026-11-15 · 契约：contracts 1.0（无破坏性变更）

## 新增能力

1. 批量回填：`generate adopt --all [--limit]` 把全部 succeeded 且未回填的生成任务逐条回填为项目产物；Web API `POST /api/generate/jobs/adopt`；与单任务回填一致，写 `<阶段目录>/generations/` 凭证并登记 `state.stage_artifacts`。批量场景下最后统一 `register_artifacts`，避免逐条覆盖阶段产物摘要。
2. 生成平台流程节点：`generate_refresh`（查询/刷新状态）与 `generate_adopt`（回填结果）可放入流程图编排；节点类型由 15 增至 17，参数 `job_id` 或 `all=true`（`limit`），支持 `stage`/`kind`/`note`，dry-run 只计划。
3. 生成面板筛选：任务列表可按状态筛选（全部/排队中/成功/失败/已取消/dry-run/计划/已回填），并提供「回填全部已成功」按钮；筛选切换后行内详情/刷新/重试/回填操作仍可用。

## 验证

- 新增 10 项测试（批量回填 3、生成节点 6、批量回填 Web API 1），全量 316 项通过（`Ran 316 tests ... OK`）。
- CLI 冒烟：`generate adopt --all`、`generate refresh --all`、`flow validate`（17 类节点）。
- Web 冒烟：生成面板状态筛选、批量回填；CI（compile/tests/doctor/brand-guard）全 PASS。

## 限制

- 批量回填只处理最近 `limit` 条已成功且未回填任务，失败任务不进入结果；回填仍只登记凭证 JSON，不下载平台视频。
- 流程节点需显式给出 `job_id` 或 `all=true`，不会自动轮询、自动重试或自动回填。
- 仍需平台 env key 与网络；mock/dry-run 任务没有平台状态可查。

## 升级说明

- 直接替换发行包内文件即可；无状态迁移、无契约破坏性变更。旧流程图与节点参数继续可用，新增节点类型需在 `content/flow-node-types.json` 中可见。
- 校验：`python workbench.py version` 应为 `workbench 1.10.0 (contracts v1.0)`；`python workbench.py doctor` 9 项全 OK；`python scripts/run_ci.py` 全 PASS。
