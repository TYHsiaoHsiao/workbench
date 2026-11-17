# workbench 2.28.0 发行说明（M41：Web 操作台扩展）

## 本版本做了什么

- **操作台新增 7 个白名单操作（共 24 个）**：项目摘要 `project_summary`、生成任务刷新 `generate_refresh`、批次报表推送 `batch_report_push`、队列告警 `queue_alerts` / `queue_alerts_push`、批次历史 `flow_batches`、环境自检 `doctor`。
- **操作历史**：进程内环形缓冲（最多 50 条）+ `GET /api/ops/history?limit=`；前端「最近操作」显示状态、耗时与时间，失败红字。
- **批量执行**：`POST /api/ops/batch`（items ≤ 20，顺序执行、单项失败不中断、返回逐项结果）；前端勾选复选框后「批量执行选中」。

## 验证

- 测试：`Ran 546 tests ... OK`（新增 `tests/test_ops.py` 7 项与 Web 端点测试）。
- 覆盖率：行 81.1%（7418/9147）、分支 51.29%（3496/6816），双门禁通过。
- 本地九步 CI、打包冒烟、回滚演练均通过。
- 文档链接检查、FR 映射检查通过。

## 兼容性

- 契约无变化，纯增量（MINOR）；CLI 行为不变，操作台与 CLI 等价。
- 操作历史仅存于服务进程内存，重启后清空。
