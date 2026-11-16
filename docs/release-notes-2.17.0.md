# workbench 2.17.0 发行说明（M30：检索结果精细化）

日期：2026-11-16 · 版本：2.17.0（MINOR，向后兼容） · 契约：contracts v1.0（17 份，`knowledge-search` 新增 4 个可选字段）

## 能力

1. **结果过滤与上限**
   - `min_score`（≥0，默认 0 不过滤）：过滤低于阈值的结果，仅对带分数候选生效。
   - `max_per_file`（1–10，默认 2）：同一文件最多返回条数，避免单文件霸屏。
   - `snippet_chars`（40–400，默认 120）：结果片段截断长度，超出加 `…`。
2. **查询词邻近度加权**
   - `proximity_weight`（0–2，默认 0.5）：hybrid 排序中，同片段内多个查询词出现位置越接近得分越高（`_proximity_score`，按最短跨度与 60 字归一）；0 关闭。
3. **CLI 与服务**
   - `index search --min-score 2.5 --max-per-file 1` 可临时覆盖配置。
   - `index_service` 证据卡 `report.search_config` 同步四项有效配置；`index search --json` 顶层也返回。

## 验证

- 全量 `Ran 488 tests ... OK`；行覆盖率 80.96%（6709/8287）、分支覆盖率 51.24%（3147/6142）。
- 新增 9 项测试（配置默认/上限与截断/阈值过滤/邻近度打分与权重生效/CLI/非法配置拒绝/服务报告）。
- 九步 CI 全绿（编译/文档链接/FR 映射/测试/覆盖率/doctor/冷启动基准/品牌守卫/可复现构建）。

## 使用

```bash
python workbench.py index search --query 第一幕 --mode hybrid --min-score 2.5 --max-per-file 1
# 或改 content/knowledge-search.json：
# {"min_score": 0.0, "max_per_file": 2, "snippet_chars": 120, "proximity_weight": 0.5}
```

## 限制

- `min_score` 只对带分数候选生效（LIKE 回退候选无分数，不受阈值过滤）。
- `max_per_file`/`snippet_chars` 默认值会改变既有结果密度与片段长度（属 MINOR 语义增强）。
- 邻近度加权只影响 hybrid 排序，不改变 FTS 召回口径，也不引入语义/向量检索。

## 兼容性

契约新增可选字段；CLI 新增可选参数；既有命令与 API 行为兼容，无破坏性变更。
