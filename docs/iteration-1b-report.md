# 迭代 1b 报告：A 编排硬化（0.4.0）

- 版本：workbench 0.4.0（contracts 1.0）
- 日期：2026-11-14
- 结论：迭代 1b 范围内 I1-01 ~ I1-08 全部落地，全量 118 项测试通过，本地 CI 全绿（Windows 实跑）。

## 1. 背景与范围

迭代 1a/2/2.1 打通了 B 子系统的只读检索与证据链；迭代 1b 回到 A 子系统，把「10 Skill + 4 份规则文件」的流程约束固化为可执行代码：

| 工作项 | 内容 | 状态 |
|---|---|---|
| I1-01 | 安装器：备份、幂等、回滚、配置保留 | 完成 |
| I1-02 | 初始化器：真实文档目录探测、工作台配置、项目模板 | 完成 |
| I1-03 | 意图路由：维护口令隔离、知识库触发、入口 A/B/C/D | 完成 |
| I1-04 | 门禁引擎：01/B/05/06/08、知识卡、风格卡 | 完成 |
| I1-05 | 状态卡 v2：合并字段、迁移器 | 完成 |
| I1-06 | 参考记忆 v2：统一命名、范围枚举、变更日志、旧字段迁移 | 完成 |
| I1-07 | 旧项目升级器：备份、规则更新、历史目录、保留参考记忆 | 完成 |
| I1-08 | E2E：从零走完 01–05、回退一次、升级一次 | 完成（Windows） |

## 2. 交付物

### 2.1 新增/扩展模块

| 文件 | 职责 |
|---|---|
| `packages/installer/__init__.py` | `plan_install` / `install_skills`：同名旧目录移入 `skills-backup-<ts>`；复制失败自动回滚；升级保留 `knowledge-base.json` 原字节；`--dry-run` 只演练 |
| `packages/core_router/project.py` | 文档目录探测（Windows Shell 已知文件夹 / macOS 常见路径 / 环境变量）、工作台配置、项目模板、`create_project`、状态存取、状态卡刷新 |
| `packages/core_router/gates.py` | 注册表门禁 + 条件门禁；硬门禁不可豁免；`can_advance` 返回原因；`advance` 拒绝跳过；`mark_downstream_stale` 按注册表顺序标记全部下游 |
| `packages/core_router/intent.py` | 维护口令 → 知识库 → 修订 → 阶段 → 入口 → 未知 的优先级识别，规则外置 `content/intent-rules.json` |
| `packages/core_router/migrate.py` | 旧项目迁移（状态合并、参考记忆 MD→JSON、旧 MD 改名保留、报告）与规则升级（备份、补目录、重写 AGENTS、刷新状态卡） |
| `packages/contracts/schemas/state.schema.json` | 状态卡 v2：知识桥、风格、确认文件、阶段产物、修订日志、门禁阶段字段 |
| `content/intent-rules.json` | 维护口令、知识库触发词、8 阶段关键词、直接入口、入口 A–D、修订词 |
| `packages/cli/main.py` | 重写：新增 `route` / `gate` / `next` / `install` / `migrate` / `upgrade`；`init` 改用初始化器；`doctor` 6 项自检 |

### 2.2 规则文件与目录约定

- 状态唯一事实来源：`00_project/state.json`（状态卡 v2，契约校验后才允许写入）。
- 参考记忆唯一事实来源：`00_project/reference-memory.json`；同目录 `.md` 为只读人读视图。
- 项目目录 12 项：`00_project/{history,knowledge-cards,style-cards}`、`00_inbox`、`01_story`…`06_prompts`、`05_shots/keyframes`。
- 旧项目命名（`project-status.md` / `routing.md` / `00-本地知识库参考记忆.md`）由迁移器识别，不要求用户手工改名。

## 3. E2E 验证证据

- **从零推进**：`init` → 01 门禁（`positioning_menu` + `sub_option_confirm` 硬门禁）→ `next` → 02 →（03 世界观可选，默认跳过）→ 04 → 05；每步状态版本递增、门禁自动补齐。
- **门禁不可绕过**：未通过 `next` 时退出码 1，并列出具体待通过门禁；硬门禁 `waive` 直接报错。
- **条件门禁**：入口 B 在阶段 01 自动追加 `screenplay_intake`；知识桥状态非 off 时阶段 05 自动追加 `knowledge_card_confirm`。
- **修订标记下游**：阶段 04 修订后，`stale_downstream` 标记为 05/06/07/08，并写修订日志。
- **旧项目迁移**：含 `state.json` + `project-status.md` + `routing.md` + 旧参考记忆 MD 的项目迁移后，状态合并为 v2，参考条目转为 JSON（未知字段标注「迁移待核对」），旧 MD 改名为 `reference-memory.legacy.md`，创作文件字节不变。
- **规则升级**：备份 `AGENTS.md` / `状态卡.md` / 路由与状态卡旧文件后，按模板重写 `AGENTS.md` 并刷新状态卡，写升级报告。
- **安装器**：升级时旧 Skill 目录整体入备份；失败注入（`copy_hook` 第二次调用抛错）后旧版本被恢复、新复制目录被清除。

## 4. 偏差与修复

1. **注册表 06→07 推进关系**：原数据 06 的 `downstream` 只有 `["08"]`，导致正常流程会跳过 07（表演）；已修正为 `["07", "08"]`。
2. **修订优先于阶段**：原优先级「阶段 > 修订」会把「回到剧本阶段修改第 8 场」误判为普通阶段指令；已把修订提到阶段之前，规则文件不变。
3. **下游过期算法**：原实现沿 `downstream[0]` 逐步前进，会漏掉可选/分支阶段；改为按注册表顺序标记当前阶段之后的全部阶段。
4. **状态卡 v2 字段可选**：新字段全部为可选，旧项目未迁移前仍可校验通过，降低迁移门槛。

## 5. 测试与 CI

- 新增 50 项测试：gates 10、intent 12、project 12、installer 7、migrate 4、E2E 5。
- 全量：`Ran 118 tests ... OK`；本地 CI（编译 → 测试 → doctor → brand-guard）退出码 0。
- 品牌守卫：全仓扫描 0 命中，新增文件全部品牌中性。

## 6. 已知局限与下一步

- **macOS 未实跑**：路径逻辑使用 `pathlib` 与环境变量，代码层兼容；但本轮 E2E 只在 Windows 上执行，macOS 需补一次实跑（迭代 4 发布前）。
- **安装器范围**：只安装 Skill 目录树；课程包 ZIP 解包、10 Skill 完整性校验仍由原安装脚本负责，后续可合并为一个入口。
- **参考记忆 .md 视图**：当前 `.md` 为初始化时生成的只读快照；JSON 变更后不会自动重渲染，后续可加 `render` 命令。
- **迁移启发式**：旧 MD 字段解析为尽力而为，未知值标注「迁移待核对」，需人工复核一次。
- 下一迭代建议：迭代 3（C 风格服务：200 导演色卡 → 风格画像 → 多模型适配），随后迭代 4 试点与发布。
