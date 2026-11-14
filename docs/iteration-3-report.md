# 迭代 3 报告：C 风格服务（0.5.0）

- 日期：2026-11-14
- 范围：PRD §9.5 `I3-01` ~ `I3-05`
- 结论：全部完成；新增 23 项测试，全量 141 项通过；本地 CI 全绿；真实项目 E2E 通过。

## 1. 背景与决策

C 子系统（200 位导演色卡包）此前是「有资产、无接口」：SKILL.md 依赖人工阅读，提示词模板分散在
每位导演的 `prompts/` 下，工作台无法解析、校验、复用。迭代 3 的目标是把这些资产变成：

```text
风格包（只读） → 注册表（契约） → 风格画像（契约） → 工具提示词（结构校验） → 注入记录（可复核）
```

关键决策：

1. **只读引用，不复制素材**：工作台只保存元数据与相对路径，避免 1.3GB 图片进入仓库与版权扩散。
2. **注册表即契约**：`style-registry.schema.json` 固化 200 条元数据；构建脚本可重跑、可校验。
3. **镜像分级**：按数据完整度给 A/B/C，让「可用但有小问题」的 B 级导演不被埋没，也不冒充 A 级。
4. **显式挂载**：风格绝不默认注入；先 apply（写卡+状态）再 inject（结构校验+记录）。
5. **结构校验只针对用户正文**：风格卡的 lens/framing 自带运镜词，若校验组合文本会误判「一镜一运镜」。

## 2. I3-01 ~ I3-05 完成对照

| 工作项 | 交付物 | 状态 |
|---|---|---|
| I3-01 风格注册表 | `scripts/build_style_registry.py`、`content/style-registry.json`、`style-registry.schema.json`、`docs/style-registry-report.md` | ✅ |
| I3-02 风格卡与工具适配 | `packages/style_service/registry.py`、`service.py`、`adapters.py`（8 工具） | ✅ |
| I3-03 06/08 挂载与注入记录 | `apply_profile` / `inject_prompt`；`00_project/style-cards/style-<id>-profile.json`、`style-<id>-injection-<stage>-<tool>.json`；`state.style` | ✅ |
| I3-04 提示词结构校验器 | `adapters.TOOL_SPECS` v1 + `validate_prompt`（必填/禁词/时长/运镜/连续性） | ✅ |
| I3-05 E2E | Windows：真实项目 `悬疑短片PoC`，apply 001 → inject 06/mj → inject 08/seedance_2_0 | ✅ |

## 3. 注册表构建结果

- 扫描风格包：`D:\AI影视工作台\导演视觉风格色卡整合版SKILL200位`（只读，10 类 × 20 导演）。
- 产物：`content/style-registry.json` **200 条 / 10 分类**；质量 **A 140 / B 60 / C 0**；重复主色调色板 **0 组**。
- 每条含：编号/中英文名/分类/目录、调色板（6 主 + 4 情绪 + 占比和）、`style_profile`、
  关键词、4 类模板行数、参考文件数、分级与问题清单。
- 构建报告问题统计：失效图链 59、目录名含空格 6、目录名后缀 1、目录名 Unicode 1、
  manifest 旧绝对路径 79（仅标记，不写入仓库）、缺少来源说明 147（有色卡但无 `reference_sources.md`）。

### 修复过程

| 问题 | 根因 | 处理 |
|---|---|---|
| 200 条全部 `missing_references` | 参考文件在 `assets/references/`，初版按导演根统计 | 改为识别 `assets/references` 与 `references` 两种布局 |
| 版权标记误判 | 色卡主文档无「版权/©」字样 | 改用 `reference_sources.md` 存在性 + manifest 历史绝对路径风险标记 |
| 目录命名问题未分级 | A 级原先只校验调色板 | A 级增加「目录名无空格/后缀/Unicode 异常」条件，异常降为 B |

## 4. 工具适配与校验

`TOOL_SPECS` v1 覆盖 8 工具（06：mj/banana/sd；08：seedance_2_0/seedance_2_5/h3/runway/pika），
校验内容包括：必填结构、必需标记（如 `--ar`、`overall_soundscape`）、禁用标记（banana 禁 `--`）、
否定句式、视频连续性禁令词、时长上限、运镜种类上限。

调试修复：

- `normalize_tool` 原先替换 `_`/`-` 后再查别名，`seedance_2_0`、`gpt-image` 无法识别 → 改为紧凑比较。
- 注入记录打印时 `UnicodeEncodeError: 'gbk' codec can't encode character '\ufeff'`
  （PowerShell `Set-Content -Encoding utf8` 写出 BOM）→ 读取用 `utf-8-sig`，CLI 启动时 stdout/stderr
  `reconfigure(encoding="utf-8", errors="replace")`。
- E2E 08 报「运镜种类超限：推近、环绕、手持（上限 1 种）」：组合提示词里混入风格卡构图/镜头文本
  → 校验范围改为用户正文，风格卡只作为前缀并在文档中说明理由。

## 5. E2E 验证证据（Windows）

项目：`D:\AI影视工作台\projects\悬疑短片PoC`

```text
style apply 001            → 00_project/style-cards/style-001-profile.json
                             条目：希区柯克 / AlfredHitchcock / 分类 黑色悬疑与冷调惊悚 / 6 色调色板
style inject 06/mj         → style-001-injection-06-mj.json        (正文 sha256 前缀 82aca7b94e32)
style inject 08/seedance_2_0 → style-001-injection-08-seedance_2_0.json (正文 sha256 前缀 3691a54df627)
state.style                → {"status": "on", ...}
注入记录内容               → 组合提示词 = 【风格卡】七段 + 空行 + 用户正文；issues = []
```

记录中 `prompt_sha256` 为用户正文（去首尾空白）的字符串哈希，便于复核「同一正文 → 同一记录」；
`state.style.note` 每次重写为「风格 <编号> <名称>；最近注入 <阶段>/<工具>」，不累积历史。

## 6. 质量与测试

| 项目 | 结果 |
|---|---|
| 新增风格测试 | 23 项（registry 4 / adapters 5 / service 9 / CLI 5）全部通过 |
| 全量测试 | `Ran 141 tests in 24.343s`，OK |
| doctor | 7 项检查全 OK（新增 style-registry） |
| 品牌守卫 | 0 命中（仓库全部文本） |
| 契约 | 7 份 schema 全部可加载、注册表校验通过 |

## 7. 已知局限

1. 提示词模板内容来自外部风格包，工作台只统计行数、不评估模板质量；
2. 注册表是构建快照，风格包更新后需重跑 `build_style_registry.py`；
3. 色卡图/剧照不进入仓库，跨机协作需携带风格包；
4. 结构校验保证合规，不评价创意质量；
5. 注入记录能被复核，但需要执行侧配合登记「是否实际喂给模型」；
6. 只在 06/08 挂载风格，其他阶段不注入；
7. macOS 路径探测已实现，但本轮 E2E 只在 Windows 实跑。

## 8. 下一步

- **迭代 4：试点项目与发布**（PRD §9.6）：用真实短片走 01–08 全流程，收集耗时/返工/确认点数据，
  验证「阶段推进 + 门禁 + 知识挂载 + 风格挂载」的组合效果，再决定是否对外发布 0.5.0+。
- 可选增强：风格卡与 06 资产表联动（资产清单引用 style_id）；注入记录汇总报表。
