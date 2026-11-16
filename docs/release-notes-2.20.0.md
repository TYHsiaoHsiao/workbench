# 发行说明 2.20.0（M33：告警外送增强与批次趋势报表）

## 重点能力

1. **通知外送增强（重试/退避 + 飞书格式）**
   - `--webhook-format feishu`：把失败通知包装为飞书自定义机器人文本消息 `{"msg_type":"text","content":{"text":"【AI 影视工作台】…"}}`。
   - `--webhook-retries 0–3`：发送失败按 1s/2s/3s 固定退避重试，结果中 `attempts` 记录实际次数；重试耗尽不阻断队列/批次。
   - 适用于 `flow queue alerts`、`queue run`、`queue daemon`、`flow batch`；公共实现见 `packages/flow/notify.py`。
2. **批次趋势报表**
   - `flow batch-report --project <项目> [--limit 20] [--format md|csv] [--out 路径] [--json]`。
   - 汇总最近 N 批次的图运行数、成功/失败、成功率与平均耗时；可写入文件或输出 JSON 摘要。

## 验证

- 新增 12 项测试合计 509 项；行覆盖率 81.04%（6897/8511），分支覆盖率 51.38%（3238/6302）。
- 九步 CI 全 PASS（含文档链接、FR 追溯、覆盖率、可复现构建）；发行包冒烟与回滚演练 2.19.0→2.20.0→2.19.0 通过。

## 使用示例

```bash
python workbench.py flow batch-report --project 我的短片 --format md --out batch-report.md
python workbench.py flow queue alerts --project 我的短片   --webhook-format feishu --webhook-retries 2   --webhook-url https://open.feishu.cn/open-apis/bot/v2/hook/<token>
```

## 已知限制

- 报表只读汇总，不含图表渲染/跨项目聚合。
- webhook 无熔断/去重；飞书自定义机器人若启用签名校验，当前不支持签名计算（可自行用中转服务）。
- 重试为固定退避，不含指数退避或跨网络重试队列。

## 兼容性

- 仅新增可选 CLI 参数与只读报表模块，无契约变更，向后兼容。
