# 知识服务（knowledge_service）

> 版本 0.3.1 · 契约 `knowledge-card` v1.0 · 状态：只读适配 + 有限正文回退 + 证据质量评分（未重建索引）

## 1. 定位

知识服务是**可选挂载点**，不是第 09 个创作阶段：

- 默认关闭；只有用户明确说出「调用本地知识库 / 知识库B / 知识库C / 匹配本地参考 / 只查方法书」等口令，才允许检索；
- 检索结果先产出**知识卡**（`knowledge-card` 契约），用户确认后才可能进入参考记忆；
- 服务只读现有知识库索引与正文文件，**不写入、不重建、不移动**知识库本体。

## 2. 分层与模块

```text
CLI（workbench.py knowledge ...）
  └─ service.py   KnowledgeService：发现库根 → 探测 → 检索 → 知识卡
       ├─ adapter.py   元数据候选（documents 表，只读 URI）
       └─ evidence.py  文件级证据（正文逐行扫描，路径防越界）
```

### 2.1 adapter.py（元数据适配）

- 目标文件：知识库根下的 `knowledgeIndex.sqlite`；
- 结构指纹：schema 必须为 `aistudio-md-2`（`metadata.schema`），并存在 `documents` 表；
- 连接：`sqlite3.connect("file:...?mode=ro", uri=True)`，每次操作显式关闭（Windows 下不关闭会锁文件）；
- 候选召回：`documents.path/title` 的 `LOWER(...) LIKE` 匹配查询词，按分类白名单 + 路径排除 + 命中词数打分排序；
- 回退文件列举：`list_scan_files()` 在 lane 允许分类内按 `(category, path)` 固定顺序列出文档行，不按查询词过滤，供有限正文回退使用；
- 分类通道（lane）：

| lane | 允许分类 | 用途 |
|---|---|---|
| `screenplay` | 05 / 06 / 07 | 参考剧本 |
| `method_book` | 08 | 编剧方法书 |
| `cultural_fact` | 01–04 | 神话、历史、民俗、国风事实 |
| `style_reference` | 无 | 预留给风格服务，当前不检索 |

- 默认排除路径片段：`90-`、`10-`、`99-`、`待精筛`、`正版待导入`、`影视研究期刊`、`新加入待分类`。

### 2.2 evidence.py（证据链）

- 只接受 `.md` / `.txt`，单文件默认上限 8MB；回退扫描可用 `max_bytes` 把单文件读取压到更小（默认 256KB）；
- `resolve_under()` 拒绝 `..` 越界；读不到/超限/未命中一律返回空，**绝不编造**；
- 命中按行记录：`{path, page: "行 N", snippet, hit}`，同一文件最多取 `max_hits` 条；
- v0.3.1 起内部另带 `quality` 评分（不写入知识卡），见 2.5。

### 2.3 service.py（编排）

- 库根发现顺序：环境变量 `AI_FILM_KB_ROOT` → `~/.ai-film-workbench/config.json` 的 `knowledge.root` → 从当前目录与工作区根向上/向下探测 `knowledgeIndex.sqlite`；
- 流程：查询词提取 → 元数据候选 → 正文证据 → 召回不足时有限正文回退 → 组装并自校验知识卡；
- 状态：

| status | 含义 | 是否可声称命中 |
|---|---|---|
| `ok` | 有文件级证据 | 可以（需用户确认） |
| `no_evidence` | 有候选，但正文/回退均未命中 | 不可以 |
| `no_candidates` | 元数据与回退都没有候选 | 不可以 |

- 阶段 → 参考范围：01–05 → `story_01_05`，06 → `image_06`，07 → `performance_07`，08 → `camera_08`。

### 2.4 有限正文回退（召回不足时）

- 触发条件（任一）：证据数少于 `evidence_limit`（`evidence_below_limit`）；或某个查询 lane 的元数据候选为 0（`lane_without_candidates`）；
- 预算：`fallback_max_files`（默认 200 份文件）、`fallback_max_bytes`（默认 256KB/文件）；只扫 `.md` / `.txt`；文件必须真实存在且位于库根之下；
- 顺序：按 `(category, path)` 固定顺序，保证可复现；已由元数据取证的路径不重复扫描；
- 发现命中后：追加行级证据，并把该文件加入 `candidates`；最终候选与证据分别按 `candidates_limit` / `evidence_limit` 截断；
- 报告新增：`report.fallback`（enabled/trigger/files_listed/files_scanned/files_missing/hits/budget）与 `report.lane_candidates`；
- 关闭方式：`--no-fallback`，或 `fallback=False`；预算为 0 时也等价关闭。

### 2.5 证据质量与精度过滤（v0.3.1）

- 每条证据在内部带 `quality` 评分，**不写入知识卡**（契约仍是 path/page/snippet/hit 4 字段）；
- 评分要素：有效命中词数；整行含结构语境词（情节/剧情/结局/身份/伏笔/结构/第三幕…）加 2；含常见叙事搭配（反转设计/情节反转/身份反转/结局反转/核心事件…）加 4；同一行命中 ≥2 个查询词（共现）加 3；
- 动作/物件误命中过滤：「反转身」「反转过来」「反转过去」「反转身体」「反转方向」等模式内的命中不计为证据，并计入 `report.evidence_quality.filtered_mis_hits`；
- 置信策略：高置信证据（≥3 分）不少于 2 条时，丢弃纯字面低置信证据，计入 `low_confidence_dropped`，避免噪声进入知识卡；
- 知识卡证据按评分降序（同分按路径/行号稳定排序）；候选列表也按证据最高分重排；
- 报告字段 `report.evidence_quality`：`considered` / `filtered_mis_hits` / `phrase_hits` / `cooccurrence_hits` / `top_score` / `high_confidence_evidence` / `low_confidence_dropped` / `sorted_by`。

## 3. CLI

```bash
# 探测知识库（不检索）
python workbench.py knowledge probe [--kb-root DIR] [--json]

# 检索并生成知识卡
python workbench.py knowledge search \
  --project 项目名 --stage 05 \
  --problem "当前阶段要解决的问题" \
  --query "screenplay:悬疑 反转 短片" \
  --query "method_book:三幕式结构 悬念" \
  --fallback-files 200 --fallback-bytes 262144 \
  --out 项目/00_project/knowledge-cards/05-candidates.json [--json]
```

- `knowledge probe`：`issues` 非空退出码 1；不兼容布局（非 `aistudio-md-2`）同样退出 1；
- `knowledge search`：成功（含 `no_evidence`）退出 0；服务错误退出 1；
- 回退开关：`--no-fallback` 关闭；`--fallback-files` / `--fallback-bytes` 调整预算（默认 200 份 / 256KB）；
- 知识卡可用 `python workbench.py validate 卡片.json --schema knowledge-card.schema.json` 单独校验。

## 4. 知识卡字段（v1.0）

- `card_id` / `project` / `stage` / `created_at`；
- `query_profile`：`problem` + `queries[{lane,query,weight}]`；
- `evidence`：`path`（相对知识库根）/ `page`（行号）/ `snippet` / `hit`；
- `candidates`：元数据候选列表；
- `selected_documents` / `deep_read_selected`：用户在确认环节指定；
- `confirmed`：空串 = 未确认，知识卡不得交给创作阶段；
- `scope`：参考适用范围。

## 5. 只读保证

- 连接 `mode=ro`；不执行任何写 SQL；
- 实测：检索前后 `knowledgeIndex.sqlite` 的 SHA-256 与 mtime 完全不变；
- 该保证由 `tests/test_knowledge_service.py::test_search_does_not_modify_knowledge_base` 持续守护。

## 6. 已知局限

1. 现有 FTS5 表（`search`）由 APP 私有 tokenizer 写入，外部 `MATCH` 命中为 0，**不能复用**；
2. 元数据候选依赖文件名/标题含查询词，中文剧本文件名通常不含主题词 → 05/06 剧本召回明显弱于 08 方法书；
3. 有限正文回退已补足「未召回文件」的一部分（预算内按固定顺序扫描），但仍受预算与顺序限制，不等于全库正文检索；
4. 回退使用字面子串匹配，仍可能误命中（如「手镯反转」「突然反转」未覆盖）；v0.3.1 已过滤「反转身」类明确动作误命中、按结构语境/叙事搭配/共现加权，并在高置信证据足够时丢弃低置信证据，但语义级精度仍需后续模型/规则增强；
5. 因此当前版本保证「**不虚构命中**」；召回率在预算内显著提升（见 `docs/iteration-2-recall-report.md`），完整召回需按契约重建索引（中期方案 B）。
