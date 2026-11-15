# workbench 2.3.0 发行说明（M15：队列定时调度、取消/重排与后台守护）

> 版本：2.3.0 · 日期：2026-11-15 · 契约：v1.0（15 份；`flow-queue` v0.1 新增可选字段）

## 能力

- 定时执行：`flow queue add --at 2026-11-15T20:00` 入队后到点才执行；`flow queue run`/daemon 只处理到期条目，队列表与 summary 显示 `scheduled`/`canceled`。
- 取消与重排：`flow queue cancel <queue_id>` 仅取消 pending 条目；`flow queue move <queue_id> --before/--after/--index` 调整执行顺序（`order` 重赋 0..n-1）。
- 后台守护：`flow queue daemon --interval 30 --limit 5 [--until-empty] [--all-projects]` 周期执行到期条目，Ctrl+C 停止。
- Web/前端：`POST /api/queue/<id>/cancel`、`POST /api/queue/<id>/move`；运行面板队列列表显示「顺序/计划时间」，pending 行提供上移/下移/取消。

## 验证

- 新增 10 项测试（queue：定时跳过/计划执行/取消/重排 before-after-index/非法参数 8 项；Web API 2 项），全量 `Ran 351 tests ... OK`。
- CLI 冒烟：`flow queue add --at`、`flow queue cancel`、`flow queue move --index 0`、`flow queue daemon --until-empty`。
- doctor 9 项全 OK（contracts 15、flow 17 节点/4 模板/6 契约）。

## 限制

- 定时使用本机时钟；daemon 需保持进程常驻，停止后到期条目不会自动执行。
- 取消/重排只作用于 pending 条目；daemon 不自动重试失败条目。
- `flow-queue` 新增字段均为可选，旧队列文件与旧调用保持兼容。

## 升级

- 无需迁移：既有 `00_project/workflows/queue.json` 直接兼容；旧条目无 `scheduled_at`/`order` 时按立即执行与创建顺序处理。
