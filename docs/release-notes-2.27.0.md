# workbench 2.27.0 发行说明（M40 Web 操作台）

## 能力

- **操作台（Ops Console）**：顶栏「实操指引」升级为操作台，17 个白名单操作、8 类：
  - 开工：`quickstart_demo`、`practical_check`；
  - 项目：`project_list`；
  - 知识库：`index_build`、`index_info`、`index_verify`、`index_search`；
  - 生成：`generate_providers`、`generate_plan`、`generate_submit`；
  - 流程：`batch_run`、`batch_report`；
  - 队列：`queue_add`、`queue_run`；
  - 快照：`snapshot_create`、`snapshot_list`、`rollback_apply`（危险，默认 dry-run + 二次确认）。
- 每个操作带参数 schema（必填/默认值/枚举/说明），执行时进程内调用 CLI 并捕获输出；返回 `exit_code`、`output` 与可解析的 JSON `data`。
- Web API：`GET /api/ops`、`POST /api/ops/run`。

## 验证

- 全量 538 项测试通过；`tests/test_webui_api.py::test_ops_endpoints` 覆盖列表/danger 标记/执行/缺参/未知 op。
- 覆盖率（2.27.0）：行 80.83%（7333/9072）、分支 50.99%（3442/6750），双门禁通过。
- 本地九步 CI、打包冒烟、回滚演练（2.26.0 → 2.27.0 → 2.26.0）通过。

## 兼容性与限制

- 纯新增：CLI、契约、数据目录均无破坏性变更；`/api/ops/run` 只接受注册表内的操作，不开放任意 shell。
- 执行输出截断为 12000 字符；长任务仍建议使用 CLI/后台守护。
- 操作台与 CLI 等价，同一项目请避免同时执行多个写操作（状态锁仍生效）。
