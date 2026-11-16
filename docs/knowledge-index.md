# 知识库索引维护（M21–M30）

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
- 检索：查询 ≥ 3 字用 FTS5 `MATCH`（bm25 排序 + `snippet`）；1–2 字自动退化为 `LIKE`（转义 `% _ \`）。中文按 3 字滑窗切分，请尽量使用连续短语。M24 起 `search_index` 支持 `mode="hybrid"`（默认）：合并 FTS 与 LIKE 候选，按标题/路径/短语/词项覆盖率加权后降序，供 `index search --mode hybrid` 与知识服务证据卡使用。

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

## 7. 混合排序（M24）

`search_index(out_dir, query, *, limit=8, mode="auto")` 支持四种模式：

| 模式 | 行为 |
|---|---|
| auto | 兼容旧行为：≥3 字走 FTS（bm25 原始分），短查询 LIKE |
| fts | 强制 FTS；<3 字符时报错（请用 like/hybrid） |
| like | 强制 LIKE 子串匹配 |
| hybrid | 合并 FTS(limit×3)+LIKE(limit×2) 候选，按 (path, heading) 去重后加权排序 |

hybrid 分数 = 基础分 + 标题命中 2.0 + 路径命中 1.0 + 短语命中 1.5 + 词项覆盖率 1.0；score 仅用于排序，不承诺跨查询可比。短查询（<3 字）由 LIKE 候选兜底。

## 8. 检索配置与查询扩展（M27）

`content/knowledge-search.json` 由 `knowledge-search.schema.json` 校验，字段：

- `weights`：`heading`/`path`/`phrase`/`coverage`，默认 `2.0/1.0/1.5/1.0`（仅 hybrid 排序使用）。
- `synonyms`：查询词扩展（如「悬念」→「悬疑/紧张」）；hybrid 对每个变体各检索一次后合并去重。
- `stopwords`：查询词过滤（如「的/了/是」）。
- `expand_limit`：同义词扩展上限（默认 8；hybrid 实际查询变体最多 4 个）。
- `synonym_weight`：同义词扩展项在词项覆盖率中的权重（0–1，默认 0.5；原词固定 1.0，M29）。
- `min_score`：结果最低分数阈值（≥0，默认 0 表示不过滤；仅对有分数的候选生效，M30）。
- `max_per_file`：同一文件最多返回条数（1–10，默认 2；M30）。
- `snippet_chars`：结果片段最大字符数（40–400，默认 120，超出截断加省略号；M30）。
- `proximity_weight`：查询词邻近度加权（0–2，默认 0.5；0 关闭；仅 hybrid 排序生效，M30）。

```bash
python workbench.py index search --query 悬念 --mode hybrid --config content/knowledge-search.json
python workbench.py index search --query 悬念 --mode hybrid --weights heading=3,path=1,phrase=2,coverage=1
```

`--weights` 覆盖配置权重、`--config` 指定其他配置文件；`doctor` 要求 `knowledge-index` 与 `knowledge-search` 两份契约、且默认配置可加载。限制：配置只影响排序与单轮扩展，不改变 FTS 召回口径；不做语义/向量检索。

## 9. 健康巡检（M29）

`python workbench.py index health --out index [--source <源目录>] [--json]` 只读巡检：

- 结构一致性：元数据 documents/chunks 与数据库计数、FTS 行数与 chunks 对齐、FTS5 MATCH 探针。
- 数据卫生：无主分块（chunks 有而 documents 无）、空分块、重复文档路径。
- 陈旧度（可选 `--source`）：把源目录文件与索引记录按 mtime_ns 比对，统计新增/变更/删除（列表各限 20 条）。
- 输出 `status`（healthy/problems）、`stats`、`checks[]`、`stale`、`suggestions[]`；存在问题返回退出码 1，建议通常是全量重建或 `index build --incremental`。

```bash
python workbench.py index health --source 06-全球电影节获奖剧本
python workbench.py index health --out index --json
```

## 10. 结果精细化（M30）

hybrid 检索在原有「标题/路径/短语/词项覆盖率」加权之外，加入**查询词邻近度**：

- `_proximity_score`：同片段内多个查询词出现位置越接近得分越高（0–1，按最短跨度与 60 字归一），由 `proximity_weight`（0–2，默认 0.5）加权进总分。
- `_apply_result_limits`：所有模式统一后处理——`min_score > 0` 时过滤低于阈值的结果；同一文件最多 `max_per_file` 条；片段超过 `snippet_chars` 截断并加 `…`。
- CLI 覆盖：`index search --min-score 2.5 --max-per-file 1`；配置文件同样支持四项字段（`content/knowledge-search.json` 已提供默认值）。
- 返回 JSON 顶层附带 `min_score`/`max_per_file`/`snippet_chars`/`proximity_weight` 便于核对；`index_service` 的 `report.search_config` 同步暴露。
