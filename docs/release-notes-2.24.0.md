# workbench 2.24.0 发行说明（M37：飞书卡片通知与批次趋势 SVG 图）

- 版本：2.24.0（contracts v1.0）；迭代：M37（迭代 40）
- 发布日期：2026-11-16

## 能力

1. 飞书卡片通知：`--webhook-format feishu_card` 发送 `msg_type=interactive` 卡片，告警红色 / 报表绿色，标题含事件名，正文含摘要与失败图；适用于 `flow batch-report --push`、`flow queue alerts/run/daemon`、`flow batch --webhook-url`。
2. 批次趋势 SVG：`flow batch-trend --project --limit --out trend.svg`；`report.py::batch_trend_svg` 生成自包含 SVG（成功/失败条形、图例、批次 ID 尾 8 位标签，无外部资源）。
3. Web：`GET /api/batches/trend?project=&limit=10` 返回 SVG；批次历史面板「趋势 SVG」按钮直接下载 `batch-trend.svg`。

## 验证

- 测试：新增 6 项，全量 `Ran 524 tests ... OK`
- 覆盖率：行 81.23%（7088/8726）、分支 51.74%（3362/6498），双门槛通过
- 本地 CI 九步全 PASS；发行包 `dist/workbench-2.24.0.zip` 与 SHA256；打包冒烟、回滚演练（2.23.0→2.24.0→2.23.0）、可复现构建均通过

## 使用示例

```bash
python workbench.py flow batch-report --project 我的短片 --format md --push \
  --webhook-url https://open.feishu.cn/open-apis/bot/v2/hook/xxx --webhook-format feishu_card

python workbench.py flow batch-trend --project 我的短片 --limit 10 --out batch-trend.svg
```

## 限制

- 趋势图基于批次摘要（最近 N 次），不包含节点级明细；
- 飞书卡片显示受群机器人版本与安全策略影响，不支持时请回退 `feishu` 文本格式；
- SVG 为静态快照，需要刷新时重新导出即可。

## 兼容性

纯新增 webhook 格式与命令/端点，旧配置与旧脚本不受影响；无契约破坏性变更（contracts 仍为 v1.0，schema 未改）。
