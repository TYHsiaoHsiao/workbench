# 2.9.0 发行说明（M21 知识库索引维护）

> 发布日期：2026-11-15 · 版本：workbench 2.9.0（contracts v1.0）

## 能力

- **索引契约**：`knowledge-index.schema.json` v0.1（index_id/build_mode/source_root/engine/计数），写入前契约校验。
- **按契约重建**：`packages/knowledge_service/index_builder.py` 把 Markdown 知识库分块（标题段落 + 900 字/80 重叠）写入 SQLite FTS5 trigram。
- **增量维护**：`index build --incremental` 按路径 + mtime 复用未变文件、重索引变更、删除消失文档。
- **检索**：`index search` ≥3 字走 FTS5（bm25 + snippet），短查询 LIKE 回退。
- **校验**：`index verify` 校验元数据契约、库计数一致与 FTS 可查询性。
- **CLI/doctor**：`workbench.py index build/info/verify/search`；`doctor` 增加索引检查（10 项，含 FTS5 trigram 探针）。
- **隔离**：索引产物默认 `index/`（gitignore，manifest/release 排除），知识库本体只读。

## 验证

- 新增 `tests/test_knowledge_index.py` 14 项，全量 **401 项测试通过**。
- 真实数据：`06-全球电影节获奖剧本` 61 文档 → 10,542 分块；`index search 第一幕` 命中《赎罪》剧本 2 条；增量重建本次索引 0、复用 61、移除 0。
- `doctor` 10 项全 OK（16 份契约、flow 17 节点/4 模板/6 契约、generate 4 provider、index 项）。
- CLI 冒烟 build/info/verify/search/incremental 全部退出 0；品牌守卫 0 命中。

## 限制

- 索引为独立新链路，尚未接入 `knowledge_search` 节点/服务（当前服务仍只读外部 `knowledgeIndex.sqlite`）。
- 全量知识库（13,272 文件/10.5 GB）需按子目录建库；索引与源文件同量级占用磁盘。
- 分块为规则切分，无语义/向量检索；增量只按路径+mtime 判断。
- 中文 trigram 对 1–2 字查询退化为 LIKE，精度与性能低于 FTS。

## 升级

- 无破坏性变更；新增可选 CLI 与契约，旧项目/旧命令行为不变。
- 首次使用：`python workbench.py index build --source <知识库子目录>` → `index verify` → `index search`。
- 发行包不含 `index/` 数据；升级后需在目标机器重建索引。
