# 发行说明 1.0.1（2026-11-15）

1.0.1 是 1.0.0 之后的第一个补丁版本，来源是真实项目试点的摩擦清单（《死亡外科医生》从零到 done）。
本版本不改变契约、不改变阶段路由，只补齐四个"必须手工绕路"的运维缺口，并新增 18 项回归测试。

## 一、本版新增（P2 四项）

### 1. 产物登记 CLI

```bash
python workbench.py artifact register --project <名或路径> \
  --stage 01 --kind 大纲 --path 01_story/synopsis.md \
  [--path 01_story/characters.md] [--note "备注"] [--next-action "下一步"] [--json]
```

- 支持项目内相对路径、glob（`01_story/*.md`）与项目内绝对路径；
- 自动逐文件计算 SHA-256 与字节数，写入 `state.stage_artifacts[stage]`；
- 追加 `revision_log`（`artifact_registered`），并刷新状态卡；
- 路径不存在或越出项目目录会报错，不写半份状态。

### 2. 知识桥状态 CLI

```bash
python workbench.py knowledge bridge --project <名或路径> --status requested|on|off \
  [--card 00_project/knowledge-cards/01-candidates.json] \
  [--references 参考方法001,参考方法002] [--note "备注"] [--json]
```

- 只写 `state.knowledge_bridge`，不触发检索；
- 仍遵守"知识桥不是阶段、默认关闭"的边界；
- 与 `reference list` 配合，可以完整记录知识卡 → 采用 → 启用的链路。

### 3. 跨阶段内容一致性检查

```bash
python workbench.py check --project <名或路径> --content [--json]
```

检查项：

| 检查 | 级别 |
|---|---|
| `style.status=on` 但风格卡文件缺失 | 错误 |
| `knowledge_bridge.status=requested/on` 但 `last_card` 缺失 | 错误 |
| `knowledge_bridge.status=on` 但 `confirmed_references` 为空或不在 `state.references` | 错误 |
| `stage_artifacts` 引用的文件不存在 | 错误 |
| `01_story/treatment.md` 场次预算与 `05_shots/*-shot-plan*.md` 的「场次时长预算」不一致 | 错误 |
| acting 交接时长与 treatment 预算不一致 | 提示 |
| `stale_downstream` 非空 | 提示 |

输出结构：`{registry_errors, project, errors, warnings, ok}`；有错误时退出码 1，仅提示时退出码 0。

### 4. 风格批量注入 API

```bash
python workbench.py style inject-batch --project <名或路径> --batch batch.json \
  [--out-dir 输出目录] [--json]
```

batch 文件格式：

```json
{
  "stage": "08",
  "tool": "seedance_2_5",
  "items": [
    {"shot": "SH-01", "prompt": "【整体】…【光影】…【镜头】…【声音】…【对白】…"},
    {"shot": "SH-02", "prompt": "…"}
  ]
}
```

- 逐条执行与单条注入相同的结构校验与风格卡组合；
- 任一条不合格时整批拒绝，并列出 `SH-xx: 原因`；
- 写一份批量记录 `00_project/style-cards/style-<id>-injection-<stage>-<tool>-batch.json`（含每条 `prompt_sha256` / `combined_sha256` / 字数），解决逐条覆盖、无法留痕的问题；
- 可选 `--out-dir` 同时导出每条 `.txt`。

## 二、测试与验证

- 单元测试：149 → **167 项全部通过**（新增 `test_artifact.py` 8 项、`test_content_check.py` 7 项、`test_style_service.py` 批量 2 项，另含既有回归）。
- 本地 CI：`compile / tests / doctor / brand-guard` 四项 PASS，退出码 0；品牌守卫扫描 0 命中。
- 真实项目回归：试点 C 项目在 1.0.1 下 `check --content` 通过；对 `artifact register`、`knowledge bridge`、`inject-batch` 均做了临时项目冒烟。

## 三、升级说明

- 无破坏性变更：契约版本仍为 `contracts 1.0`，`state.schema.json` 未改字段；
- 旧项目可直接使用新命令，无需迁移；
- 若你的项目曾手工改过 `state.json`，建议先跑一次 `check --content` 再继续推进阶段。

## 四、已知限制

- `check --content` 的时长比对基于文本正则，适用于当前 Markdown 表格格式；格式自由改写后可能漏检；
- 产物存在性核验只针对含目录的路径；旧版自由文本摘要里的裸文件名无法确定目录，会跳过核验（建议用 `artifact register` 重新登记）；
- 批量注入记录是"一次调用一份"，如需逐镜独立记录仍可继续用单条 `style inject`；
- 知识桥状态 CLI 只维护状态字段，不负责检索与知识卡生成（这两步仍由 `knowledge search` / 人工确认完成）。

## 五、变更文件

- `packages/core_router/project.py`：`register_artifacts`、`update_knowledge_bridge`；
- `packages/style_service/service.py`：`inject_batch`；
- `packages/cli/main.py`：`artifact register`、`knowledge bridge`、`style inject-batch`、`check --content`；
- 新增测试：`tests/test_artifact.py`、`tests/test_content_check.py`、`tests/test_style_service.py`（批量）。
