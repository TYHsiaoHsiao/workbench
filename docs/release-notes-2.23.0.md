# workbench 2.23.0 发行说明（M36）

## 新增

- 批次报表推送：`flow batch-report --push --webhook-url <url>`（`event=batch.report`；复用飞书格式 `--webhook-format feishu` 与 `--webhook-retries 0–3`）。
- Web：`POST /api/batches/report/push`，批次历史面板新增「推送报表」按钮。
- 告警静默窗口状态：`GET /api/queue/alerts` 的摘要新增 `state`（`dedupe_minutes`/`last_pushed_at`/`silence_until`/`suppressed`），CLI `flow queue alerts` 与 Web 告警面板展示。

## 验证

- 全量测试 518 项通过；九步 CI 全 PASS；`manifest.json`、发行包与 `.sha256` 一致；回滚演练 2.22.0→2.23.0→2.22.0 通过。

## 兼容性

- MINOR：仅新增可选 CLI 参数、只读 Web 端点与展示字段，无契约变更，向后兼容。
