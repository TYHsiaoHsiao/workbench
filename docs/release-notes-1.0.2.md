# 发行说明 1.0.2 — 工作台体验补丁

- 版本：`1.0.2`（契约仍为 v1.0，无破坏性变更）
- 日期：2026-11-15
- 范围：试点 C 真实项目反馈的 P3 摩擦项修复，不改阶段模型、契约与命令语义

## 一、这版解决什么

真实项目（《死亡外科医生》）完成后归纳的摩擦中，有三项属于"体验成本"而非正确性问题：

1. 项目分散在多个根目录，需要 manually 找路径；
2. 风格注册表里 B/C 级的待核元数据（失效图链、目录命名）在列表/详情里看不见；
3. 批量注入只留一份整批记录，逐镜追溯需要翻批量 JSON。

## 二、新增能力

### 1. 跨项目总览

```bash
python workbench.py project list                 # 默认扫描文档目录默认根 + 仓库同级 projects/
python workbench.py project list --json          # 脚本友好
python workbench.py project list --root D:\A --root D:\B
```

输出：名称、阶段、版本、入口、风格状态、知识桥状态、最后更新时间；损坏项目跳过并在末尾提示。

### 2. 风格质量提示

- `style list`（文本）：显示 A/B/C 分级数量；非 A 级条目追加「待核：问题1、问题2…」。
- `style show`（文本）：非 A 级或有问题时输出「质量提示：B 级，待核问题 2 条：…」。
- JSON 输出保持不变（`list` 的 JSON 中 `issue_labels` 为新增字段，向后兼容）。

### 3. 批量逐镜注入记录

```bash
python workbench.py style inject-batch --project <项目> --batch batch.json --per-shot-records
```

在原有 `style-<id>-injection-<stage>-<tool>-batch.json` 之外，为每条提示词写
`style-<id>-injection-<stage>-<tool>-<shot>.json`（含 shot、正文 sha256、组合 sha256、字数、组合提示词）。

### 4. `init` 下一步引导

`init` 完成后打印：项目根目录、下一步命令（`check --content` / `gate list` / `project list`）以及
`AI_FILM_PROJECTS_ROOT` 固定项目位置的提示。

## 三、验证

- 单元测试：**170 项全部通过**（167 + 新增 3：project list / init 提示 / 批量逐镜记录）。
- 本地 CI：编译、测试、doctor（7 项）、品牌守卫全 PASS，退出码 0。
- 品牌守卫：全仓库扫描 0 命中。
- 兼容性：契约 v1.0 不变；`style list --json` 仅新增 `issue_labels` 字段；其余命令行为不变。

## 四、升级方式

1. 覆盖仓库文件后运行 `python scripts/run_ci.py`；
2. 已有项目无需迁移（state v2 字段未变）；
3. 如需逐镜注入记录，重跑 `style inject-batch --per-shot-records` 即可。

## 五、已知限制

- `project list` 只识别含 `00_project/state.json` 的工作台项目；旧目录需先 `migrate`；
- 风格质量提示只反映注册表构建时的问题标记，不替代色卡人工审阅；
- 逐镜记录会随镜头数增加文件数（36 条约 36 份小 JSON），需要时再开启。
