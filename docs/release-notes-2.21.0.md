# 发行说明 2.21.0（M34：批次报表 Web 化与告警静默窗口）

- 发布日期：2026-11-16
- 版本：2.21.0（MINOR，向后兼容；无契约变化）
- 全量测试：512 项通过；行覆盖率 81.1%（6944/8562）、分支覆盖率 51.42%（3262/6344）

## 新增能力

1. 批次报表 Web 化：只读 `GET /api/batches/report?project=<项目>&limit=<N>&format=md|csv`，返回批次汇总与报表文本；Web 批次历史面板新增「报表 MD」「报表 CSV」「报表预览」三个按钮。
2. 告警静默窗口：`flow queue alerts --dedupe-minutes N`（默认 30，`0` 关闭）——相同告警（失败通知条数与失败图集合一致）在窗口内只外送一次，状态记录在 `00_project/workflows/queue-alerts-state.json`，结果新增 `suppressed`。

## 使用示例

```bash
python workbench.py flow batch-report --project 我的短片 --format md --out batch-report.md
python workbench.py flow queue alerts --project 我的短片 --webhook-url http://127.0.0.1:9/hook --dedupe-minutes 30
```

Web：`flow serve` 打开工作台 → 右侧批次历史 → 「报表 MD / 报表 CSV / 报表预览」。

## 限制

- 报表为只读快照，最多 20 个批次；Web 预览不写入磁盘。
- 告警去重指纹为失败图集合 + 条数；失败集合变化会立即重发。
- `--dedupe-minutes 0` 关闭去重。

## 兼容性

无契约变更；CLI/Web 新增可选参数与只读接口，默认行为（去重 30 分钟）在重复告警场景下减少外送次数。
