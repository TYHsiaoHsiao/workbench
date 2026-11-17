# workbench 2.25.0 发行说明（M38：实操上线包）

日期：2026-11-17
类型：MINOR（新增 CLI 命令与文档，不改契约）

## 目标

让工作台从「开发可用」变为「可实操上线」：一条命令准备项目与流程图，一条命令自检，配套实操指引与文档。

## 新增能力

### 1. `workbench.py quickstart <名称>`

- 一键创建项目（复用 `init` 骨架，支持 `--project-root/--entry/--mode`）
- 若项目无流程图，自动实例化 `tpl-full-flow`（01→08 默认流程）
- 输出下一步命令清单（自检、启动 Web、校验、预演、生成平台）
- 非交互、可重复执行：同名项目自动复用；`--skip-graph` 可跳过建图；`--force` 覆盖
- `--json` 输出 `{ok, project, created, stage, graph_id, next_commands, guide}`

### 2. `workbench.py practical-check --project <项目>`

面向实操作的 8 项自检：项目状态、阶段注册表、流程图（校验首图）、知识库、本地索引、风格库（200 导）、生成平台 provider/key、Web 启动命令。

- 输出 `[OK]/[WARN]/[FAIL]` 与可执行修复建议
- 无 `[FAIL]` 退出码 0；`--json` 输出 `{ok, summary, checks, next_commands}`

### 3. Web「实操指引」面板

顶栏新增「实操指引」按钮，内置 7 步速查（建项目→自检→预演→逐阶段→接平台→复盘→文档），不依赖后端新 API。

### 4. 文档

新增 `docs/practical-guide.md`（10 分钟从零到第一条提示词，含命令、检查表与常见问题）。

## 验证

- 全量单元测试：531 项通过（新增 6 项 M38 测试）
- 本地九步 CI 全 PASS（文档链接 / FR 映射 / 覆盖率 / doctor / 基准 / 品牌守卫 / 可复现构建）
- 覆盖率：行 81%+ / 分支 51%+（阈值 80%/50%）
- 发行包与回滚演练按既有流程验证

## 使用示例

```powershell
python workbench.py quickstart 我的短片 --project-root "D:/AI影视工作台/projects"
python workbench.py practical-check --project "我的短片"
python workbench.py flow serve --project "我的短片" --port 8899
```

## 兼容性

- 契约版本不变（contracts v1.0）
- 既有命令全部保持兼容；新增命令为纯增量
- Web 静态资源新增面板，不影响既有交互

## 已知限制

- quickstart 传入 `--project-root` 时项目不在默认项目根，后续命令建议用完整路径
- practical-check 的知识库/索引检查为可选能力，WARN 不阻塞
- 真实平台提交仍需自行配置 API key 并遵守平台条款
