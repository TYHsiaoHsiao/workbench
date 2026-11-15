# 发行说明：workbench 1.6.0（可视化节点工作台 M7）

- 版本：1.6.0（契约 1.0）
- 日期：2026-11-15
- 状态：M7 已完成

## 本版能力

- 条件分支节点 `condition`：`when` 表达式（state.stage/state.version/iteration 比较），只走 true/false 一支；未选分支下游在执行记录中标记 skipped。
- 循环节点 `loop`：`max_iterations`（1–10）与 `until` 表达式，body 单链按迭代展开；步骤记录 `iteration`、循环节点记录 `iterations`。
- 运行基线：`flow baseline set/show/clear`；`flow diff --baseline [--fail-on-regression] [--max-regressions] [--max-delta-ms]` 支持回归阈值与 CI 退出码。
- 产物快照：`project snapshot/snapshots/artifacts-diff`；Web 预览面板按钮与差异文本；快照只记录路径、sha256、大小。
- 项目摘要缓存：`GET /api/projects/<name>/summary` 按 state/workflows/runs/artifacts mtime 签名缓存，`?refresh=1` 绕过。
- Web：运行面板「存基线」「对基线对比」；项目预览「创建产物快照」「产物差异」。

## 验证

- 新增 15 项测试（条件 5、基线 2、产物 3、控制流 2、Web API 3），全量 262 项通过。
- `doctor` 8 项通过；本地 CI（compile/tests/doctor/brand-guard）全绿；品牌守卫 0 命中。
- CLI 冒烟：条件剪枝、循环展开、基线回归退出码、产物快照差异。

## 兼容与升级

- 契约仍为 1.0；flow-graph / flow-run / flow-node-types 新增字段均为可选。
- 旧流程图与项目无需迁移；未使用的 condition/loop 节点不会影响原执行路径。

## 已知限制

- 循环只支持单链 body 且不能嵌套。
- 条件表达式仅支持预定义比较形式，不支持任意布尔/函数表达式。
- 运行对比按 node_id 对齐；图结构变化较大时会出现 added/removed 噪声。
- 产物快照不复制内容，仅记录指纹与大小；差异视图不能展示文件内容 diff。
