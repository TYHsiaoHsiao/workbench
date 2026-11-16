# 发行说明 2.19.0（M32）

> 发布日期：2026-11-16 · 版本级别：MINOR（新增可选能力，向后兼容）

## 新增能力

- **告警摘要外送**：`flow queue alerts --webhook-url <url>` 聚合最近的队列失败通知，并向该地址 POST JSON：
  `event=queue.alerts.digest`，载荷含 `count`、`latest_at`、`last_message`、`failed_graphs`、`message`。
  外送失败不会抛出异常，CLI 输出「告警摘要外送失败: …」并以退出码 1 结束（本地 JSONL 与聚合结果不受影响）。
- **巡检退出码**：`flow queue alerts --fail-if-failures` 在存在失败通知时返回退出码 2，便于 cron/巡检脚本判断；
  无失败时返回 0。`--json` 分支退出码一致。
- **Web 一键恢复**：批次历史面板新增「恢复全部失败图」按钮，依次重跑最近最多 5 个失败批次的失败图，
  完成后提示累计恢复数量并刷新运行历史与批次列表。

## 验证

- 新增 4 项测试，合计 **497 项**全部通过。
- 行覆盖率 **80.89%（6802/8409）**、分支覆盖率 **51.22%（3195/6238）**，双门槛通过。
- 九步 CI（含文档链接、FR 追溯、覆盖率、可复现构建）全 PASS；发行包冒烟与回滚演练 2.18.0→2.19.0→2.18.0 通过。

## 使用示例

```bash
python workbench.py flow queue alerts --project 我的短片 --limit 20 --json
python workbench.py flow queue alerts --project 我的短片 --webhook-url https://example.test/hook
python workbench.py flow queue alerts --project 我的短片 --fail-if-failures --json
```

## 兼容性

- 仅新增可选 CLI 参数、只读聚合函数与前端按钮；无契约变更，`flow-queue` 等 schema 不变，向后兼容。
- 告警摘要仍基于本地 JSONL 通知日志；一键恢复最多处理最近 5 个失败批次；webhook 为单次尝试、无重试/退避。
