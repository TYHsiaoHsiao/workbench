# 知识库索引维护（M21 / 2.9.0）

> FR-10 基础版：把 Markdown 知识库按契约重建为 SQLite FTS5 索引，并提供增量维护与检索命令。
> 索引产物默认 `index/`（仓库内、已 gitignore、不入发行包）；知识库本体保持只读。

## 1. 命令

```bash
# 按契约重建索引（全量）
python workbench.py index build --source "../../知识库/06-全球电影节获奖剧本"

# 增量：复用未变文件、重索引变更、删除消失文档
python workbench.py index build --source <目录> --incremental

# 查看 / 校验 / 检索
python workbench.py index info
python workbench.py index verify
python workbench.py index search --query 第一幕 --limit 5
```

- 默认输出 `workbench/index/`，可用 `--out <目录>` 覆盖；`--json` 输出结构化结果。
- `build` 缺 `--source` 时会尝试文档目录探测（与知识服务一致的 `discover_kb_root`）。

## 2. 索引契约（knowledge-index.schema.json v0.1）

元数据文件 `knowledge-index-meta.json` 与库 `knowledge-index.sqlite` 同目录，字段：`contract_version`、`index_id`（`idx-<UTC 时间>-<hex>`）、`build_mode`（full/incremental）、`source_root`、`engine`（sqlite-fts5 + trigram + schema_version）、`created_at`/`updated_at`、`documents`、`chunks`、`files_total`、`files_indexed`、`files_reused`、`files_removed`、`bytes_source`。写入前经 `contracts.validate` 校验，`index verify` 会复验。

## 3. 分块与检索

- 分块：按 Markdown 标题段落聚合；单块 ≤ 900 字符，超长按 900 切分、相邻块重叠 80 字符。
- 库表：`documents(path, sha256, bytes, mtime_ns, chunks)`、`chunks(id, path, heading, text)`、`chunks_fts`（FTS5，`tokenize='trigram'`）。
- 检索：查询 ≥ 3 字用 FTS5 `MATCH`（bm25 排序 + `snippet`）；1–2 字自动退化为 `LIKE`（转义 `% _ \`）。中文按 3 字滑窗切分，请尽量使用连续短语。

## 4. 增量策略

`--incremental` 且现有库/元数据有效时：按相对路径 + `mtime_ns` 判断，未变文件跳过并计 `files_reused`，变更文件重索引，源中已消失的文件（及其分块/FTS 行）删除；否则全量重建。`index_id` 保留原值、`updated_at` 更新。

## 5. 规模与限制

- 全量知识库约 13,272 个 Markdown / 10.5 GB（含 `10-小说库` 9.8 GB），不建议一次性全量建库；按子目录（如 `05`/`06`/`08`）分别建库。
- 索引产物与源文本同量级，需预留磁盘；SQLite 需支持 FTS5 trigram（Python 内置 SQLite ≥ 3.34，当前 3.12 环境可用）。
- 本迭代索引是独立新链路，尚未接入 `knowledge_search` 节点/服务（服务仍只读外部 `knowledgeIndex.sqlite`）；接入与语义检索为后续候选。
