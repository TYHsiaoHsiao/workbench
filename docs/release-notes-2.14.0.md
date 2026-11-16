# 发行说明 2.14.0（M27：索引检索配置增强）

日期：2026-11-16 · 版本：2.14.0（MINOR，向后兼容）

## 能力

- **检索配置契约**：新增 `knowledge-search.schema.json` 与默认 `content/knowledge-search.json`（`weights`、`synonyms`、`stopwords`、`expand_limit`）。
- **配置化排序**：`load_search_config` + `_merge_weights`，hybrid 按 `heading/path/phrase/coverage` 权重排序；`normalize_query_text` 做 NFKC/空白归一。
- **查询扩展**：同义词变体参与 hybrid 检索（最多 4 个变体），停用词过滤；`index_service.search_index_card` 透传配置并在 report 暴露摘要。
- **CLI**：`index search --config <path>`、`--weights heading=3,path=1,...`（非法键/格式/负数退出 1）；`doctor` 要求 2 份索引契约且默认配置可加载。

## 验证

- 新增 17 项测试，全量 **459 项通过**；targeted 55 项。
- 覆盖率：行 **80.94%（6489/8017）**、分支 **50.86%（3004/5906）**，双门槛通过。
- CI 九步全绿（约 311s）；发行包与回滚演练见发布流程记录。

## 使用

```bash
python workbench.py index search --query 悬念 --mode hybrid --config content/knowledge-search.json
python workbench.py index search --query 悬念 --mode hybrid --weights heading=3,path=1,phrase=2,coverage=1
```

## 限制

- 配置只影响排序与单轮同义词扩展，不改变 FTS 召回口径；无语义/向量检索。
- 同义词扩展最多 8 项/查询（默认），hybrid 实际变体上限 4；配置错误会显式报错。
