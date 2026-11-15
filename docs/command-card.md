# 命令卡（v1.4.0）

> 所有命令在 `workbench/` 目录下执行：`python workbench.py <命令>`。
> Python >= 3.10，无第三方运行时依赖。退出码：`0` 成功，`1` 校验失败/门禁拦截，`2` 参数错误，`3` 环境不可用。

## 1. 环境与自检

| 命令 | 作用 |
|---|---|
| `python workbench.py version` | 版本号 + 契约版本 |
| `python workbench.py doctor` | 8 项自检：Python、目录骨架、11 份契约、阶段注册表、意图规则、风格注册表、flow（10 节点/4 模板/4 契约）、品牌词表 |
| `python workbench.py check` | 校验阶段注册表；`--project <名或路径>` 同时校验项目 `state.json` 与参考记忆 |
| `python workbench.py check --project 项目名 --content` | 跨阶段内容一致性：风格卡/知识卡/产物文件存在性、`confirmed_references` 子集、treatment↔shot-plan 时长、下游过期提示（1.0.1） |
| `python workbench.py brand-guard` | 品牌禁用词扫描；`--json` 输出结构化报告 |
| `python scripts/run_ci.py` | 本地 CI：编译 → 全量测试 → doctor → brand-guard |

## 2. 项目生命周期

| 命令 | 作用 |
|---|---|
| `python workbench.py init 项目名 --entry A` | 创建项目骨架（12 个目录 + `00_project/state.json` + 参考记忆 JSON/MD + 状态卡） |
| `python workbench.py project list`（加 `--stats` 输出流程/运行/待门禁/产物统计，1.4.0） | 跨项目总览：扫描默认项目根与仓库同级 `projects/`（可多次 `--root`），显示阶段/版本/入口/风格/知识桥/更新时间（1.0.2） |
| `python workbench.py init 项目名 --entry B --force` | 覆盖已存在项目（默认拒绝覆盖） |
| `python workbench.py route "只做CINEDANCE"` | 意图路由：维护口令 > 知识库请求 > 直接入口 > 修订 > 阶段 > 入口 |
| `python workbench.py gate list --project 项目名` | 查看当前阶段门禁状态 |
| `python workbench.py gate pass <门禁id> --project 项目名 --note 说明` | 通过门禁（硬门禁不可豁免） |
| `python workbench.py gate fail <门禁id> --project 项目名 --note 原因` | 标记门禁失败 |
| `python workbench.py next --project 项目名` | 推进阶段；门禁未通过时退出码 1 并列出原因 |
| `python workbench.py artifact register --project 项目名 --stage 01 --kind 大纲 --path 01_story/synopsis.md` | 登记阶段产物：SHA-256 + 字节数写入 `stage_artifacts`，追加修订日志并刷新状态卡（1.0.1，支持 glob / 多 `--path`） |
| `python workbench.py reference list --project 项目名 --stage 05` | 查看当前阶段自动加载的参考方法编号 |
| `python workbench.py export --project 项目名` | 导出项目 ZIP（含 `export-metadata.json`） |
| `python workbench.py restore 归档.zip --dest 目标目录` | 还原导出包（校验路径穿越、目标非空拒绝覆盖） |

## 3. 旧项目迁移与升级

| 命令 | 作用 |
|---|---|
| `python workbench.py migrate --project 旧项目路径` | 旧目录结构 → 工作台结构：合并状态、生成 `reference-memory.json`、备份到 `00_project/history/migrate-*` |
| `python workbench.py upgrade --project 旧项目路径` | 规则升级：备份后重写 AGENTS 与状态卡、补齐目录、保留创作文件（备份在 `00_project/history/upgrade-*`） |

## 4. Skill 安装

| 命令 | 作用 |
|---|---|
| `python workbench.py install --source ../skills --dry-run` | 预演安装（10 个 Skill 校验） |
| `python workbench.py install --source ../skills` | 安装/升级 Skill：旧目录移入 `skills-backup-*`、保留 `knowledge-base.json` 字节、失败自动回滚 |

## 5. 知识服务（B 挂载，默认关闭）

| 命令 | 作用 |
|---|---|
| `python workbench.py knowledge probe` | 只读探测知识库（schema、文档数、FTS 可用性、问题列表） |
| `python workbench.py knowledge search --project 项目名 --stage 05 --problem "问题" --query "screenplay:悬疑 反转"` | 检索 → 知识卡（`ok` / `no_evidence` / `no_candidates`） |
| `... --fallback-files 200 --fallback-bytes 262144` | 调整有限正文回退预算 |
| `... --no-fallback` | 关闭正文回退，只用元数据候选 |
| `... --out 项目/00_project/knowledge-cards/05-candidates.json` | 保存知识卡（默认只打印） |
| `python workbench.py knowledge bridge --project 项目名 --status requested --card 00_project/knowledge-cards/01-candidates.json` | 记录知识桥状态（off/requested/on）与确认编号（1.0.1，不触发检索） |

## 6. 风格服务（C 挂载，默认不注入）

| 命令 | 作用 |
|---|---|
| `python workbench.py style list --json` | 200 位导演；可按 `--category 01` / `--quality A` 筛选；文本模式显示分级数量与待核问题（1.0.2） |
| `python workbench.py style show 001` | 查看风格卡详情（调色板、光线、镜头、工具适配）；非 A 级会显示「质量提示」（1.0.2） |
| `python workbench.py style resolve 希区柯克` | 按编号/中英文名/目录解析 |
| `python workbench.py style validate 001 --tool mj --text "提示词正文"` | 结构校验（必填字段、禁用词、模型约束） |
| `python workbench.py style apply 001 --project 项目名` | 生成风格卡 `00_project/style-cards/style-001-profile.json` 并更新 `state.style` |
| `python workbench.py style inject 001 --project 项目名 --stage 06 --tool mj --prompt-file p06.txt` | 注入风格前缀 + 校验正文 + 写注入记录（阶段仅 06/08） |
| `python workbench.py style inject-batch --project 项目名 --batch batch.json [--out-dir 目录]` | 批量注入：整批校验、失败整批拒绝、写一份 `*-batch.json` 批量记录（1.0.1） |
| `python workbench.py style inject-batch ... --per-shot-records` | 额外写逐镜注入记录 `style-<id>-injection-<stage>-<tool>-<shot>.json`（1.0.2） |

## 7. 可视化节点工作流（flow）

| 命令 | 作用 |
|---|---|
| `python workbench.py flow serve --project 项目名 [--port 8899]` | 启动本机可视化工作台（打印带 token 的 URL；`--no-token` 仅本机调试） |
| `python workbench.py flow templates [--json]` | 模板库（4 套：从零到成片 / 入口接力 / 知识增强 / 风格注入） |
| `python workbench.py flow new --project 项目名 [--template tpl-full-flow] [--graph 流程id] [--force]` | 新建流程图（默认骨架或模板实例化） |
| `python workbench.py flow list / show / validate --project 项目名 [--graph 流程id]` | 流程列表 / 详情 / 校验（契约 + 语义 8 条） |
| `python workbench.py flow run --project 项目名 --graph 流程id [--dry-run/--live] [--mode full/to_node/single] [--node 节点id] [--yes]` | 运行（默认按图设置，建议先 dry-run；`--yes` 自动确认断点） |
| `python workbench.py flow run --project 我的短片 --graph flow-main --live --retries 2` | 真实运行并允许节点失败自动重试（`--retries 0–3`，默认 0；写状态节点重试可能重复副作用） |
| `python workbench.py flow runs --project 项目名 [--limit 20]` | 运行历史（状态/步骤/失败/恢复来源） |
| `python workbench.py flow recover --run run-id --project 项目名 [--restore-state] [--yes]` | 失败运行恢复（可选回滚 `state_snapshot_before` 快照后重跑） |
| `python workbench.py flow replay --run run-id --project 项目名 [--json]` | 运行回放（每步耗时、最慢节点、失败定位） |
| `python workbench.py flow export --project 项目名 --graph 流程id --out flow.json` | 导出流程图 JSON（也可 `--file flow.json` 原样输出） |
| `python workbench.py flow import --project 项目名 --file flow.json [--graph 新id] [--force]` | 导入流程图（先校验，非法不落盘） |
| `python workbench.py flow batch --project 项目名 --all [--dry-run/--live] [--yes]` | 批量运行项目内全部流程图 |

## 8. 契约校验

| 命令 | 作用 |
|---|---|
| `python workbench.py validate 文件.json --schema state.schema.json` | 按契约校验任意 JSON |

## 9. 典型工作流

```bash
# 从零到 08
python workbench.py init 雨夜回声 --entry A
python workbench.py gate pass positioning_menu --project 雨夜回声
python workbench.py next --project 雨夜回声
...
python workbench.py export --project 雨夜回声

# 既有剧本接力（B 入口）
python workbench.py init 旧剧本接管 --entry B
python workbench.py migrate --project 旧项目          # 仅旧目录项目需要
python workbench.py knowledge search --project 旧剧本接管 --stage 05 \
  --problem "接管检查与生产资料补齐" --query "method_book:三幕式结构 悬念"

# 风格注入（06/08）
python workbench.py style apply 001 --project 雨夜回声
python workbench.py style inject 001 --project 雨夜回声 --stage 06 --tool mj --prompt-file p06.txt

# 可视化节点工作流（先预演，再 live）
python workbench.py flow serve --project 雨夜回声
python workbench.py flow new --project 雨夜回声 --template tpl-full-flow --name 从零到成片
python workbench.py flow run --project 雨夜回声 --graph flow-main --dry-run
```
