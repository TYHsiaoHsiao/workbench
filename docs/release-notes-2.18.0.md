# workbench 2.18.0 发行说明（M31：批次/队列运维收尾）

**日期**：2026-11-16 · **版本**：2.18.0（MINOR，无契约变更）

## 1. 本版能力

| 能力 | 说明 |
|---|---|
| cron 表达式预览 | CLI `flow cron-preview --expression "*/5 * * * *" --count 3 [--json]`；Web `POST /api/cron/preview`；前端运行面板「cron 预览」小组件显示下一次触发时间（零依赖 5 段解析，非法表达式退出 1） |
| 失败告警聚合 | CLI `flow queue alerts [--limit 20] [--json]`；Web `GET /api/queue/alerts`；聚合失败通知条数/最近时间与消息/失败图 Top5，前端「失败告警」面板可手动刷新 |
| 批次历史趋势 | Web 批次历史面板新增最近 10 批次成功/失败 SVG 趋势条，便于快速识别连续失败 |

## 2. 使用示例

```bash
python workbench.py flow cron-preview --expression "*/5 * * * *" --count 3
python workbench.py flow queue alerts --project 我的短片 --limit 20 --json
```

Web：`python workbench.py flow serve --project 我的短片 --port 8899` → 运行面板「批次历史趋势」「失败告警」「cron 预览」。

## 3. 验证

- 全量测试 **493 项**通过；行覆盖率 **80.92%**（6773/8370）、分支覆盖率 **51.23%**（3178/6204）。
- CI 九步全绿；发行包冒烟通过；回滚演练 `2.17.0 → 2.18.0 → 2.17.0` 版本校验通过。

## 4. 兼容性与限制

- 无契约/状态写变化；新增 CLI 子命令与只读端点，向后兼容（MINOR）。
- 告警聚合基于本地 JSONL（无远端持久化）；cron 预览为静态计算，不注册系统计划任务；趋势图为前端示意，非统计报表。
