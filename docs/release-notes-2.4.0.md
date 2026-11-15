# 2.4.0 发行说明（M16：队列失败重试、通知外送与守护日志）

日期：2026-11-15

## 能力

- **失败重试**：`flow-queue` 契约条目新增可选 `attempts`（已重试次数）；`flow queue retry <queue_id>` 仅重置 failed 条目为 pending（attempts +1，清理批次/结果/通知字段）；`flow queue run --retry-failed N` 与 `flow queue daemon --retry-failed N` 先重置 `attempts < N` 的失败条目再执行；Web `POST /api/queue/<id>/retry` 与前端失败行「重试」按钮。
- **通知外送**：失败运行写 JSONL 通知日志 `00_project/workflows/queue-notifications.jsonl`（at/event/status/message/failed_graphs/ran）；`--notify-cmd` 可选外部命令（消息作为最后一个参数，超时 10s，失败静默）；`flow queue notifications` 与 Web `GET /api/queue/notifications` 查询。
- **守护日志**：`flow queue daemon --log-file/--rotate-bytes` 写运行日志（默认 `00_project/workflows/daemon.log`，超阈值轮转为 `.1`）。
- **前端**：队列列表显示 `· 重试 N`，失败条目提供「重试」按钮。

## 验证

- 新增 8 项测试（队列重试/通知 6、Web API 2），全量 `Ran 359 tests ... OK`；CI 全绿、品牌守卫 0 命中；doctor 9 项含 6 份 flow 契约。
- 冒烟：`flow queue retry` / `run --retry-failed 1` / `notifications` / daemon `--log-file` 参数；失败通知 JSONL 与外部命令写文件均验证通过。

## 限制

- 重试为有限手动/守护触发，无指数退避；通知外送尽力而为，外部命令失败不阻断执行。
- 通知/守护日志均在项目 `00_project/workflows/` 内；daemon 需进程常驻，不跨机器同步。
- 契约只新增可选字段与端点，默认行为不变，无需迁移。

## 升级

- 覆盖安装或解压新发行包即可；旧项目队列文件缺少 `attempts` 时按 0 处理。
