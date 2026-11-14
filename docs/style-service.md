# 风格服务（style_service）

风格服务是工作台的 C 能力层：把 200 位导演的色卡资产变成**可解析、可校验、可注入**的风格画像，
供 06 图像资产与 08 视频提示词两个阶段显式挂载。它只读引用外部风格包，**不复制、不改写**原始素材。

## 1. 定位与边界

```text
外部风格包（只读）               仓库内                 项目内（可写）
导演视觉风格色卡 ×200   →  content/style-registry.json  → 00_project/style-cards/
  SKILL.md / references/       （构建脚本生成、契约校验）      style-<id>-profile.json
  10 类 × 20 导演              200 条元数据 + 质量分级          style-<id>-injection-<stage>-<tool>.json
```

- **只读**：风格包永远只被扫描，不被修改；仓库只保存元数据（路径、色值、结构、分级、问题清单）。
- **显式**：风格注入不是默认行为。必须 `style apply` 之后才能 `style inject`；`state.style.status` 记录状态。
- **有记录**：每次注入写一条 JSON 记录（含组合提示词与正文字符串哈希），可用于复核一致性。
- **不改创作**：风格卡只作为提示词前缀；不进入参考记忆，不改变阶段路由。

## 2. 数据来源与注册表

注册表由 `scripts/build_style_registry.py` 从风格包构建：

```bash
python scripts/build_style_registry.py \
  --root "D:/AI影视工作台/导演视觉风格色卡整合版SKILL200位" \
  --out content/style-registry.json \
  --report docs/style-registry-report.md
```

查找顺序：`--root` → 环境变量 `AI_FILM_STYLE_PACK_ROOT` → 仓库同级目录（含 `SKILL.md` 且 ≥10 个 `NN_` 分类目录）。

每条 entry 包含：编号、中英文名、分类、目录、调色板（6 主色 + 4 情绪色 + 主色占比和）、
`style_profile`（定义/光线/构图/调色/避免）、关键词（构图/色彩/情绪）、4 类提示词模板行数、
参考文件数、质量等级与问题清单。

当前注册表快照：**200 条 / 10 分类；A 140、B 60、C 0；重复主色调色板 0 组。**

质量分级（构建脚本）：

| 等级 | 条件 | 用途 |
|---|---|---|
| A | 调色板完整、色卡主文档、4 份提示词模板、`style_profile` 完整，且无目录命名/图链/参考问题 | 可直接用于正式项目 |
| B | 主数据完整，但存在目录命名、失效图链、参考缺失等非阻断问题 | 可用，需人工确认问题 |
| C | 缺调色板/缺色卡/缺提示词等关键数据 | 不建议用于正式项目 |

问题统计（构建报告 `docs/style-registry-report.md`）：失效图链 59、目录名含空格 6、
目录名后缀 1、目录名 Unicode 1、manifest 旧绝对路径 79、缺少来源说明 147（不复制路径与素材，只标记风险）。

## 3. 工具适配器

`packages/style_service/adapters.py` 定义 8 种工具的提示词结构契约（`TOOL_SPECS` v1）：

| 工具 | 阶段 | 关键约束 |
|---|---|---|
| `mj`（Midjourney） | 06 | 必填 主体/风格/光线/构图；必需 `--ar`；≤6000 字 |
| `banana`（对话式生图） | 06 | 必填 主体/风格/光线；禁 `--` 参数；禁否定句式；≤4000 字 |
| `sd`（Stable Diffusion） | 06 | Positive/Negative 分离；≤4000 字 |
| `seedance_2_0` | 08 | 必填 主体/动作/场景/镜头/光线；≤15 秒；运镜 ≤1 种；≤3000 字 |
| `seedance_2_5` | 08 | 必填 整体/光影/镜头/声音/对白；≤30 秒；≤5000 字 |
| `h3`（海螺 MiniMax H3） | 08 | 必填 画面/镜头/声音；必需 `overall_soundscape`；≤30 秒；≤6000 字 |
| `runway` / `pika` | 08 | 必填主体+镜头/动作；≤10 秒；运镜 ≤1 种；≤3000 字 |

`validate_prompt(tool, text)` 返回问题列表（空列表表示通过），检查：空文本、超长、必填结构缺失、
必需标记缺失、禁用标记、否定句式（banana）、视频连续性禁令词（上一镜头/继续/同上/保持原样/同前）、
运镜种类超限或缺失、时长超限。

## 4. 风格卡与注入记录

`build_profile(entry, tool=None)` 把注册表条目映射为 `style-profile.schema.json` 契约：
`profile_id`、`director_no`、`name`、`category`、`tags`、`palette`（6 主色，含中文色名与百分比）、
`lighting`、`lens`、`materials`、`negatives`、`tool_adapters`（8 工具文本）、`quality`。

```bash
# 生成/更新风格卡（写入项目）
python workbench.py style apply 001 --project 我的短片 --tool mj

# 注入到 06 图像提示词（只校验用户正文，风格卡作为前缀）
python workbench.py style inject 001 --project 我的短片 --stage 06 --tool mj --prompt-file p06.txt

# 注入到 08 视频提示词
python workbench.py style inject 001 --project 我的短片 --stage 08 --tool seedance_2_0 --prompt-file p08.txt
```

组合规则：`combined_prompt = style_block(profile, tool) + "\n\n" + 用户正文`。
`style_block` 输出「【风格卡】名称/编号/分类、色彩比例、光线、构图/镜头、材质与色彩关键词、
禁止/避免、本工具适配」七段。

注入记录（`00_project/style-cards/style-<id>-injection-<stage>-<tool>.json`）：

```json
{
  "contract_version": "1.0",
  "style_id": "001",
  "style_name": "希区柯克",
  "stage": "08",
  "tool": "seedance_2_0",
  "prompt_sha256": "<用户正文 sha256>",
  "issues": [],
  "created_at": "2026-11-14T13:33:30",
  "combined_prompt": "【风格卡】…\n\n<用户正文>"
}
```

同一阶段/工具重复注入会覆盖该记录；`state.style.note` 记录最近一次注入摘要。

## 5. CLI 一览

```bash
python workbench.py style list --json                     # 列出 200 条（可 --category 01 --quality A）
python workbench.py style show 001 --tool mj --json       # 查看条目与工具适配
python workbench.py style resolve 希区柯克                # 名称/编号/目录名 → 条目
python workbench.py style validate 001 --tool mj --text "主体：… --ar 16:9"
python workbench.py style apply 001 --project 我的短片
python workbench.py style inject 001 --project 我的短片 --stage 06 --tool mj --prompt-file p06.txt
```

退出码沿用全局约定：0 成功、1 校验/业务失败、2 参数错误、3 环境不可用。

## 6. 只读与安全保证

- 构建脚本与目录扫描均以只读方式打开风格包文件；不写、不移动、不删除任何风格包内容。
- 注册表只保存相对路径与元数据；旧 manifest 中的历史绝对路径只作为风险标记，不写入仓库。
- 风格包素材（图片/剧照）不进入仓库，避免体积与版权扩散；如需引用，由外部包提供。
- 品牌守卫覆盖仓库全部文本（含注册表 JSON）；当前 0 命中。

## 7. 已知局限

1. **模板复用**：4 类提示词模板来自外部风格包，工作台不校验其内容质量，只统计行数。
2. **快照语义**：注册表是构建时快照；风格包更新后需重新运行构建脚本。
3. **素材外部依赖**：色卡图、剧照仍在外部包；跨机器协作需自行携带风格包。
4. **结构≠创意**：`validate_prompt` 只保证结构合规，不评价创意与画面质量。
5. **注入一致性**：记录可复核（正文哈希 + 组合提示词），但「是否真的喂给模型」需执行侧配合记录。
6. **仅 06/08 挂载**：其他阶段不注入风格，避免风格覆盖叙事判断。
7. **macOS 未实跑**：路径探测与 CLI 已做跨平台处理，但本轮 E2E 只在 Windows 验证。
