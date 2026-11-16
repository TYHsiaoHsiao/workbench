# workbench 2.16.0 发行说明（M29：索引健康巡检与同义词权重）

日期：2026-11-16 · 版本：2.16.0（MINOR，向后兼容） · 契约：contracts v1.0（17 份，`knowledge-search` 新增可选 `synonym_weight`）

## 能力

1. **索引健康巡检 `index health`**
   - 只读检查：元数据 documents/chunks 与数据库计数、FTS 行数对齐、FTS5 MATCH 探针、无主分块、空分块、重复文档路径。
   - 可选 `--source <目录>`：按 mtime_ns 比对新增/变更/删除文件（列表各限 20 条）。
   - 输出 `status`（healthy/problems）、`stats`、`checks[]`、`stale`、`suggestions[]`；problems 时退出码 1，便于 CI 或脚本阻断；文本/`--json` 两种输出。
2. **同义词权重联动**
   - `knowledge-search` 契约新增可选 `synonym_weight`（0–1，默认 0.5）：hybrid 排序中词项覆盖率按原词 1.0、同义词扩展项该权重计算。
   - `index search` 的 hybrid JSON 新增 `term_weights`（词项→权重）与 `synonym_weight`；知识服务证据卡 report 的 `search_config` 同步暴露该值。
3. **文档与测试**
   - `docs/knowledge-index.md` 新增「健康巡检」章节；命令卡/README/架构/故障排查同步。
   - 新增 9 项测试（健康巡检 6、同义词权重 3），合计 479 项。

## 验证

- 全量 `Ran 479 tests ... OK`；行覆盖率 80.85%（6638/8210）、分支覆盖率 51.02%（3095/6066），CI 双门槛通过。
- 九步 CI 全绿（编译/文档链接/FR 映射/测试/覆盖率/doctor/冷启动基准/品牌守卫/可复现构建）。
- CLI 冒烟：`index health --source ... --json` 正常返回；人为制造无主分块时退出码 1；`index search --query` 的 `term_weights` 显示「悬疑: 0.5」。

## 使用

```bash
python workbench.py index health --out index --source 06-全球电影节获奖剧本
python workbench.py index health --json
python workbench.py index search --query 悬念 --mode hybrid --json   # 查看 term_weights
```

## 限制

- 巡检只读，不自动修复；修复动作仍为 `index build`（全量或 `--incremental`）。
- 陈旧度按 mtime_ns 判断，列表各限 20 条；源目录需与索引来源一致。
- `synonym_weight` 只影响 hybrid 词项覆盖率项，不改变 FTS 召回口径，也不引入语义/向量检索。
- 与 2.15.0 兼容：无破坏性 CLI/API 变化，无新 schema（仍 17 份）。
