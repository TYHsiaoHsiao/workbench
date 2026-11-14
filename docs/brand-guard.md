# 品牌守卫（brand-guard）

## 1. 目的

确保工作台的所有**产出物**（代码、配置、文档、报告、项目模板、提示词）不出现历史品牌字样，并让这条规则在 CI 中可执行、可回归。

- **BR-01**：仓库与工作区文本中不得出现禁用词；命中即失败。
- **BR-02**：第三方语料本体（知识库中的剧本、小说正文）与其中的人物名属于版权内容，不在清理范围；允许以**目录级白名单**例外。
- **BR-03**：报告本身不得输出禁用词明文，只允许 `term#N` 形式引用词表序号。

## 2. 词表

`packages/brand_guard/wordlist.b64`：每行一个 base64 编码的禁用词。

- 仓库内**不保存明文**，避免「守卫文件自己违规」。
- 词表损坏会显式失败（`BrandGuardError`），不会静默跳过。
- 新增禁用词：把 UTF-8 字节做 base64 编码，追加一行；同步补测试。

## 3. 归一化与匹配

匹配前对「文本行」与「禁用词」同时做归一化：

1. `NFKC` 规范化（全角/半角统一）；
2. `casefold`（大小写折叠）；
3. 去除空白与分隔符 `- _ · • . | / \ ' " ` 等。

因此 `Word`、`W O R D`、`W-O-R-D`、`W_O_R_D` 都能命中。文件名也会做同样检查（`line: 0`）。

## 4. 技术白名单（safe_tokens）

外部数据格式名 `aistudio-md-2` 属于被引用的技术标识符，不是品牌字样；扫描时会从归一化行中先剔除，避免误报。配置项：

```json
"safe_tokens": ["aistudio-md-2"]
```

新增白名单必须同时满足：是外部事实/格式名、无法由本仓库修改、去掉后不影响品牌规则。**不得**用它放行品牌文案。

## 5. 目录白名单（allowlist）

`config/brand-allowlist.json` 按目录前缀例外，当前仅一条：第三方剧本/小说语料库。语义：

- 目录内文件**整树跳过**（不扫描、不计数）；
- 仅对「目录遍历」生效；显式列为 target 的单个文件仍会扫描（例如知识库说明 README 与目录表 xlsx）。

## 6. 扫描范围

`config/brand-guard.json` 的 `targets` 定义 8 个目标：

| target | 说明 |
|---|---|
| workbench-repo | 本仓库（`.`） |
| control-layer | 现有 Skill/配置文件层 |
| 4 个报告 | 分析报告、串联报告、优化 PRD、开发 PRD |
| knowledge-base-readme | 知识库 README.md |
| knowledge-catalog-spreadsheet | 知识库目录表 .xlsx |

跳过规则：跳过目录（`.git`、`__pycache__`、`node_modules` 等）、跳过扩展名（图片/PDF/压缩包/SQLite/音视频/字体）、单文件上限 20MB。表格类文件（xlsx/docx/pptx）按 zip 内 XML 成员扫描。

## 7. 报告格式

```json
{
  "ok": false,
  "scanned": 134,
  "hits": [{"path": "docs/example.md", "line": 12, "term": "term#1"}],
  "skipped": [{"path": "image.png", "reason": "skip_ext"}],
  "missing_targets": [],
  "targets": [{"name": "workbench-repo", "path": ".", "exists": true}]
}
```

- 命中只报 `term#N`，不报明文、不报上下文。
- `missing_targets` 不算失败（跨仓库使用时目标可能不存在）。
- CLI：命中退出码 `1`，运行异常退出码 `3`，通过为 `0`。

## 8. CI 集成

- 本地：`python scripts/run_ci.py` 的最后一步执行品牌守卫。
- GitHub Actions：`.github/workflows/ci.yml` 在 ubuntu/windows/macos × Python 3.11/3.12 上执行测试、doctor、brand-guard。
- 任何提交命中禁用词即阻断合并。

## 9. 已知局限

- 图片内文字、扫描版 PDF、加密 Office 文件不做 OCR，无法检测。
- 超过 20MB 的文本文件被跳过（可在配置中调整）。
- 只做「包含」判断，不做语义判断；同义词品牌变体需加入词表。
- 目录白名单是粗粒度例外，新增时需人工复核。

## 10. 后续计划

- **L2**：命令与配置层的中性化（由 M3 安装器统一迁移）。
- **L3**：目录与路径级改名（需迁移脚本 + 回滚），默认不在 M1 前执行。
- 词表版本化：在配置中加 `wordlist_version`，审计历史清理范围。
