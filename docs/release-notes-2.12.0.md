# workbench 2.12.0 发行说明（M24：索引混合排序与队列 webhook 通知）

> 版本：2.12.0（MINOR）· 日期：2026-11-15 · 迭代 27

## 能力

### 1. 索引混合排序
- `index search` 新增 `--mode auto|fts|like|hybrid`（默认 hybrid）；`search_index(..., mode=)` 同步支持。
- hybrid 合并 FTS(limit×3) 与 LIKE(limit×2) 候选，按 (path, heading) 去重后按加权分降序：基础分 + 标题命中 2.0 / 路径命中 1.0 / 短语命中 1.5 / 词项覆盖率 1.0。
- `knowledge_service/index_service.py` 证据卡检索改用 hybrid，短查询由 LIKE 候选兜底；非法 mode 与强制 fts 短查询返回可读错误。

### 2. 队列失败通知 webhook
- `flow queue run/daemon --webhook-url <URL>`：批次有失败条目时把汇总 JSON POST 到 webhook（event=queue.run、failed_graphs、message）。
- 超时/异常只记录 `webhook.error`，不改变队列执行结果；未配置时为 no-op；JSONL 通知与 `--notify-cmd` 保持原行为。

## 验证
- 全量 `Ran 429 tests ... OK`（新增 HybridSearchTest 6 项、FlowQueueWebhookTest 3 项）。
- CI 九步全绿：doc-links、fr-mapping、coverage 80.84%（≥80）、doctor 10 项、bench、brand-guard、repro。
- 发行包 `dist/workbench-2.12.0.zip`（见同目录 `.sha256`）；打包冒烟与回滚演练通过。

## 使用

```bash
python workbench.py index search --query 第一幕 --mode hybrid --limit 5
python workbench.py queue run --project 我的短片 --webhook-url https://example.com/hook
```

## 限制与兼容
- 混合排序为启发式，score 只用于排序；FTS 仍要求 ≥3 字符。
- webhook 单次 POST、无重试；URL/密钥由调用方管理。
- 无契约变更、无破坏性接口变更，向后兼容 2.11.0。
