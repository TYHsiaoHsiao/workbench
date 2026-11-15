# workbench 2.10.0 发行说明（M22：本地索引接入知识服务证据卡）

> 日期：2026-11-15 · 版本：2.10.0（MINOR，向后兼容） · 上一版：2.9.0（M21 知识库索引维护）

## 能力

- **索引证据卡**：新增 `packages/knowledge_service/index_service.py` 的 `search_index_card`，用 M21 的 `index/`（SQLite FTS5 trigram）逐查询检索，生成与外部知识库路径同结构、受 `knowledge-card.schema.json` 约束的知识卡；证据保持四字段（`path` / `page`（段落标题）/ `snippet` / `hit`），按段落去重、FTS 按 bm25 排序，未命中返回 `no_evidence` 并附可读说明。
- **CLI**：`python workbench.py knowledge search ... --index index` 改用本地索引生成证据卡；`--out` 仍写同契约卡片，`--json` 的 report 标记 `source=index` 与索引元数据（index_id/build_mode/documents/chunks/source_root）。
- **流程图节点**：`knowledge_search` 节点新增可选参数 `index`（字符串）；配置后节点走索引路径，未配置时保持原外部知识库检索，索引缺失/无命中会给出可读错误或 `no_evidence`。
- **兼容性**：无新增契约，默认行为与现有知识卡结构不变；索引目录仍不入发行包（需目标机 `index build`）。

## 验证

- `Ran 413 tests ... OK`（新增 12 项：索引证据卡服务 8、CLI 2、flow 节点 2）。
- `python scripts/run_ci.py` 九步全 PASS：doc-links、fr-mapping、测试、覆盖率 **77.37%（6017/7777 行）**、doctor、bench、brand-guard、repro。
- 发行包 `dist/workbench-2.10.0.zip`（含 `.sha256`）经 `package_smoke.py` 校验；`rollback_drill.py` 升级→回滚演练通过。

## 使用

```bash
# 1) 先构建索引（取知识库子目录，避免全量 10GB）
python workbench.py index build --source "知识库/06-全球电影节获奖剧本" --out index
# 2) 用索引生成证据卡
python workbench.py knowledge search --project 我的短片 --stage 01 \
  --problem "开场如何建立悬念" --query "建立悬念" --index index \
  --out 我的短片/00_project/knowledge-cards/01-candidates.json
# 3) 流程图节点（params 增加 index）
#    "index": "index"（相对仓库根或绝对路径）
```

## 限制

- 证据为文件级（路径/段落/片段/命中词），无语义重排或向量检索；索引未命中时仍可去掉 `--index` 走外部知识库路径。
- 索引目录不随发行包分发，部署到新机器后需自行 `index build`（或增量维护）。
- `knowledge search --index` 只读索引，不访问外部知识库，也不写参考记忆。
