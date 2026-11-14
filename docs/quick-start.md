# 快速开始（第一次拿到发行包）

本文件面向「刚拿到 `workbench-1.0.0.zip`、还没接触过工作台」的使用者。
目标：**10 分钟内**完成自检、创建第一个项目、跑通一次阶段推进。

---

## 0. 这是什么

工作台是一个**本地编排层**，不是新的创作 AI。它把已有的创作能力（Codex 的 10 个 Skill、可选本地知识库、200 位导演色卡包）组织成一条可控的流水线：

- **A 编排**：项目状态、阶段门禁、意图路由、旧项目迁移、导出还原；
- **B 知识**：只读检索本地剧本/方法书索引，产出带证据链的知识卡；
- **C 风格**：只读引用导演色卡包，生成风格卡并注入 06/08 提示词。

它解决的是「流程失控」：哪个阶段、用哪份文件、能不能推进、改了什么、下游谁受影响。

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11、macOS 或 Linux |
| Python | **3.10+**（`python --version` 确认） |
| 第三方依赖 | **无**（纯标准库） |
| 可选 | Codex（用于执行 10 个创作 Skill）、本地知识库索引、导演色卡包 |

## 2. 解压与自检

把 ZIP 解压到任意目录（例如 `D:\AI影视工作台`），得到 `workbench/` 文件夹：

```bash
cd workbench
python workbench.py version        # 期望：workbench 1.0.0 (contracts v1.0)
python workbench.py doctor         # 期望：7 项检查全部 [OK]
```

`doctor` 失败时按提示处理，常见原因见 `docs/troubleshooting.md`。

## 3. 创建第一个项目

```bash
python workbench.py init 我的第一部短片 --entry A
```

- `--entry A` 表示从零创作（B=已有剧本，C=部分资料，D=高手优化）；
- 默认位置：`<文档目录>/AI 影视工作台/projects/我的第一部短片`；
- 覆盖默认位置：环境变量 `AI_FILM_PROJECTS_ROOT` 或 `--project-root`。

创建后目录长这样：

```
我的第一部短片/
  00_project/          # state.json（唯一事实来源）、history/、knowledge-cards/、style-cards/
  00_inbox/            # 待整理素材
  01_story/            # 01 概览/梗概、02 角色、03 世界观、04 分场
  02_script/           # 05 剧本、作者剧本、生产拆解
  03_assets/           # 06 图像资产
  04_performance/      # 07 表演
  05_shots/            # 08 镜头规划、连续性台账
  06_prompts/          # 08 视频提示词
```

## 4. 跑第一个阶段

```bash
python workbench.py route "我要做一部 60 秒竖屏悬疑短片"   # 意图路由
python workbench.py gate list --project 我的第一部短片      # 查看当前阶段门禁
python workbench.py next --project 我的第一部短片           # 尝试推进（门禁未过会被拒绝）
```

创作内容由 Codex 中的对应 Skill 生成（项目 `AGENTS.md` 会指路）。工作台的职责是：

1. 生成阶段产物后登记：`stage-artifacts`、`revision_log`；
2. 逐条通过门禁：`gate pass --project … --gate <id> --note "…"`；
3. 确认无误再 `next`，进入下一阶段并自动创建新阶段门禁。

> 完整命令见 `docs/command-card.md`；阶段与门禁定义见 `content/stage-registry.json`。

## 5. 可选：接入本地知识库（B）

```bash
python workbench.py knowledge probe --kb-root "D:\...\知识库根目录"
python workbench.py knowledge search --project 我的第一部短片 --stage 05 \
  --problem "需要参考短片结构与反转设计" \
  --query "screenplay:悬疑 反转" --query "method_book:三幕式结构 悬念" \
  --out 我的第一部短片/00_project/knowledge-cards/05-candidates.json
```

- 只读，不改知识库本体；
- 只有「本地路径 + 行号 + 命中词」齐全时状态才是 `ok`，否则是 `no_evidence`（这是正确行为，不要编造命中）；
- 召回不足时会按预算做有限正文回退，可用 `--fallback-files` / `--fallback-bytes` / `--no-fallback` 调整。

## 6. 可选：接入风格（C）

```bash
python workbench.py style list --quality A --json          # 查看 200 位导演（A 级 140）
python workbench.py style apply 001 --project 我的第一部短片
python workbench.py style inject 001 --project 我的第一部短片 --stage 06 --tool mj \
  --prompt-file 06_body.txt
python workbench.py style inject 001 --project 我的第一部短片 --stage 08 --tool seedance_2_0 \
  --prompt-file 08_body.txt
```

- 风格默认不注入，必须先 `apply` 再 `inject`；
- `inject` 会做结构校验（必填字段、禁用词、时长、运镜种类）并写注入记录；
- 06 只接受图像工具（mj/banana/sd），08 只接受视频工具（seedance/h3/runway/pika）。

## 7. 常用命令速记

| 场景 | 命令 |
|---|---|
| 自检 | `version` / `doctor` / `check` |
| 品牌检查 | `brand-guard` |
| 项目交接 | `export --project <名>` / `restore <zip> --dest <目录>` |
| 旧项目迁移 | `migrate <旧项目>` → `upgrade <项目>` |
| 安装 10 个 Skill | `install --source <工程版 skills 目录> --dry-run`（确认后去掉 `--dry-run`） |
| 跑全部检查 | `python scripts/run_ci.py` |

## 8. 退出码

`0` 成功 ｜ `1` 校验失败/门禁未过/品牌命中 ｜ `2` 参数错误 ｜ `3` 环境不可用。

## 9. 遇到问题

1. 先看 `docs/troubleshooting.md`（12 类常见故障与快速恢复）；
2. 再跑 `python workbench.py doctor`，按失败项排查；
3. 门禁被拦是设计行为：`gate list` 看缺什么，补齐后再 `next`，不要手改 `state.json`。

## 10. 从旧版本升级

- 本包与 0.5.0 相比只做增量（新增 memory 加载、导出还原、文档与试点流程），`contracts 1.0` 未变；
- 已有项目无需迁移，直接 `check --project <名>` 验证即可；
- 旧项目（无 `state.json`）先 `migrate`，详见 `docs/migration.md`。
