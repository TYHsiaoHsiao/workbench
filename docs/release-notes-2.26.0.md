# Release Notes — workbench 2.26.0（M39：实操闭环增强）

- 版本：2.26.0（MINOR）
- 日期：2026-11-17
- 兼容性：契约不变；新增命令参数为纯增量

## 新增

- `workbench.py quickstart <名称> --demo`：在创建项目与默认流程图的同时，写入一份 60 秒竖屏悬疑短片演示剧本（`01_story/演示剧本-午夜来电.md`）与首条镜头提示词（`05_shots/shot-01-prompt.md`），生成命令可直接对演示素材执行 `generate plan mock`；已存在文件不会覆盖。
- `workbench.py practical-check --project <项目> --fix`：安全自动修复——缺流程图时补建默认模板（tpl-full-flow）；可选 `--source <知识库目录>` 时构建本地索引；项目状态缺失等不可自动修复项给出明确说明。`--fix` 结果以 `fixes` 数组出现在 JSON 输出，文本模式打印「已修复/跳过」。
- `docs/practical-guide.md` 增加「演示素材」与「自动修复」两节。

## 验证

- 新增 6 项单元测试（quickstart `--demo` 建素材/幂等、`--fix` 补图/保留已有图/索引跳过/缺失项目），全量 537 项通过。
- 覆盖率（行/分支）与九步 CI、打包冒烟、回滚演练结果见发行说明与 CI 记录。
- 远端矩阵：ubuntu/windows × Python 3.11/3.12（macOS 因托管 runner 排队取消暂移除，见 `docs/troubleshooting.md`）。

## 升级

- 直接替换工作台目录即可；项目数据与索引不受影响（`index/` 不在发行包内，可保留）。
