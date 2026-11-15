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
- 2.9.0（M21）索引为独立链路；2.10.0（M22）已接入知识服务：CLI `knowledge search --index <dir>` 与 flow `knowledge_search` 节点 `index` 参数可生成同契约证据卡（详见 §6）。语义检索（embedding/向量）仍为后续候选。

## 6. 接入知识服务（M22）

- CLI：`python workbench.py knowledge search --index <索引目录> --project <项目> --stage 05 --problem "..." --queries "建立悬念"`
  - `--index` 指向 `index build --out` 的输出目录（含 `knowledge-index.sqlite` 与 `knowledge-index-meta.json`）
  - 无 `--index` 时仍走外部知识库证据链（`knowledgeIndex.sqlite`），两者输出同一 `knowledge-card.schema.json`
- flow 节点：`knowledge_search` 的参数新增可选 `index`（本地索引目录）；设置后节点优先生成索引证据卡，不设置则走外部服务。
- 证据卡差异：索引模式 `evidence` 的 `page` 为分块标题（无标题时「行 1」）、`hit` 为命中查询词；证据按 (path,page,snippet) 去重，
  FTS 与 LIKE 结果混合排序（FTS 优先）。`no_evidence` 表示索引库中无命中（通常是索引建成后源/查询词变化）。
- 限制：索引模式不读取外部 `knowledgeIndex.sqlite` 的 FTS 元数据；中文检索最低 3 字（1–2 字 LIKE 回退）；索引库需先由
  `index build` 生成，路径不存在时 CLI/节点返回可读错误。
