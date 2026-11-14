# 迁移说明（v1.0）

> 适用对象：使用旧版 10-Skill 课程包 / 旧「电影项目」目录、且希望接入本工作台的项目。
> 原则：**只迁移控制层，不动创作文件**；所有迁移与升级先备份，可原样回滚。

## 1. 旧结构 → 新结构对照

| 旧文件/目录 | 新位置 | 处理 |
|---|---|---|
| `00_project/brief.md` | `00_project/brief.md` | 保留；字段并入 `state.json` |
| `00_project/project-status.md` | `00_project/project-status.md` | 字段解析后并入 `state.json`（原文件保留为备份区） |
| `00_project/routing.md` | `00_project/routing.md` | 同上；入口/阶段/模式尽力解析 |
| `00_project/reference-memory.md` | `00_project/reference-memory.json` + `.legacy.md` | 解析为契约 JSON；旧文件改名为 `reference-memory.legacy.md` |
| `AGENTS.md`（项目根） | `AGENTS.md` | 迁移只登记；`upgrade` 时替换为工作台模板（旧版本进备份） |
| `00_project/history/` | `00_project/history/` | 保留；迁移/升级备份也写这里 |
| 创作文件（`01_story/`、`02_script/`、`03_assets/` 等） | 原样 | **不修改** |

新项目目录（`init` 自动创建）：

```text
00_project/   brief.md  state.json  reference-memory.json  reference-memory.md
              history/  knowledge-cards/  style-cards/
00_inbox/  01_story/  02_script/  03_assets/  04_performance/
05_shots/(keyframes/)  06_prompts/  AGENTS.md  状态卡.md
```

## 2. 迁移命令

```bash
cd workbench
python workbench.py migrate --project "D:/旧项目路径"
python workbench.py upgrade --project "D:/旧项目路径"
python workbench.py check --project "D:/旧项目路径"
```

### `migrate` 做什么

1. 校验旧项目至少含 `00_project/`；
2. 备份：`00_project/history/migrate-<时间戳>/`（原控制文件副本）；
3. 解析 `brief.md` / `project-status.md` / `routing.md` 的字段，合并为 `state.json`（状态卡 v2），入口/阶段无法识别时用默认值并记录「迁移待核对」；
4. 解析 `reference-memory.md` 为 `reference-memory.json`（条目、状态、范围枚举；旧「适用阶段」按故事方法默认 `story_01_05`），未知值写入「迁移待核对」；
5. 补齐阶段门禁与目录，刷新 `状态卡.md`；
6. 写 `00_project/migration-report.md`（字段映射、条目数、待核对项）。

### `upgrade` 做什么

1. 校验已迁移（必须有 `state.json`）；
2. 备份：`00_project/history/upgrade-<时间戳>/`（AGENTS/状态卡/routing/project-status 的副本）；
3. 补齐 `PROJECT_DIRS` 目录；写入工作台 `AGENTS_TEMPLATE`；刷新状态卡；
4. **不修改**任何创作文件与参考记忆条目；
5. 写 `upgrade-report.md`。

## 3. 参考记忆字段映射

| 旧 Markdown 字段 | 新 JSON 字段 |
|---|---|
| 参考方法编号标题 | `id`（如 `参考方法001`） |
| 状态 | `status`（`enabled`/`disabled`/`removed`） |
| 来源名称 | `source` |
| 来源类型 | `type`（`screenplay`/`method_book`/`cultural_fact`/`other`） |
| 本地路径 | `local_path` |
| 页码与命中词 | `page_hits` |
| 可迁移方法 | `method` |
| 使用范围 | `scope`（`story_01_05`/`image_06`/`performance_07`/`camera_08`/`full`） |
| 指定阶段 | `stage` |
| 绑定项目事实 | `binding_facts` |
| 禁止借用 | `forbidden` |
| 确认记录 | `confirmed` |
| 变更记录 | `change_log` |

迁移后校验：

```bash
python workbench.py reference list --project "D:/旧项目路径"
python workbench.py reference list --project "D:/旧项目路径" --stage 05 --json
```

## 4. 回滚

- `migrate` 备份在 `00_project/history/migrate-*`；`upgrade` 备份在 `00_project/history/upgrade-*`（文件名扁平化，如 `00_project__routing.md`）。
- 回滚方式：把备份文件复制回原相对路径即可；工作台不会自动反向覆盖。
- 已用试点项目演练：`upgrade` 后从 `upgrade-*` 还原 `AGENTS.md`，字节哈希与备份一致（见 `docs/pilots/metrics.json` → `rollback_drill`）。

## 5. 迁移后检查清单

```text
[ ] python workbench.py check --project <项目>
[ ] python workbench.py gate list --project <项目>
[ ] python workbench.py reference list --project <项目> --stage 05
[ ] 打开 00_project/migration-report.md 处理「迁移待核对」条目
[ ] 确认创作文件 SHA-256 未变化（可对比迁移前后）
[ ] 如需发行备份：python workbench.py export --project <项目>
```

## 6. 已知限制

- 字段解析是启发式的：表格/列表格式支持有限，复杂格式可能需要人工核对 `migration-report.md`。
- 旧 Markdown 参考记忆中无法识别的枚举值统一写「迁移待核对」，不会静默丢弃。
- 迁移不搬运旧知识库与旧 Skill 目录；它们仍由安装器/知识服务按各自路径引用。
