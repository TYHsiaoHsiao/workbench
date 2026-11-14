# 变更日志

## [1.0.0] - 2026-11-14 — 迭代 4：试点与固化

- 参考记忆加载器 `core_router/memory.py`：阶段→范围映射（01-05 story、06 image、07 performance、08 camera），按 `status=enabled` 与 scope（含 `full`）自动加载；`reference list` CLI 命令。
- 项目导出/还原 `core_router.project.export_project / restore_project` + CLI `export` / `restore`：ZIP 内含 `export-metadata.json`；拒绝路径穿越与覆盖非空目标；还原后校验 state 并刷新状态卡。
- 试点驱动 `scripts/pilot_matrix.py`：试点 A（从零到 08，60 秒竖屏悬疑）与试点 B（B 入口接管到 05，作者剧本 SHA 不变）；迁移/规则升级、导出还原、品牌、漂移、门禁负向检查与 M1–M9 指标全部落盘 `docs/pilots/`。
- 试点 A 实测：01→02→04→05→06→07→08→done（v08），风格 001 希区柯克应用到 06/mj 与 08/seedance_2_0，05 修订后标记下游 06/07/08。
- 试点 B 实测：01→02→04→05（v04），05 自动加载 1 条参考方法，作者剧本 SHA-256 前后一致（未改稿）。
- 指标：M1 100%、M2 11/11、M3 100%（18/18，负向 4/4 拦截）、M4 平均 1.64 步/阶段、M5 100%、M6 100%、M7 0 命中（178 文件）、M8 0 漂移、M9 P0/P1=0；迁移与回滚演练（从 `history/upgrade-*` 还原 AGENTS.md 字节一致）、导出还原 19 文件一致。
- 文档定稿：`docs/command-card.md`、`docs/troubleshooting.md`、`docs/migration.md`、`docs/iteration-4-report.md`；README/architecture/PRD 同步。
- 新增 8 项测试（memory 4 / reference CLI 1 / 导出还原 3），全量 149 项通过；本地 CI 全绿；品牌守卫 0 命中；manifest 更新。
- 版本进入 `1.0.0`（契约仍为 v1.0）。

## [0.5.0] - 2026-11-14 — 迭代 3：C 风格服务

- 风格注册表 `scripts/build_style_registry.py` + `content/style-registry.json`：只读扫描 200 位导演风格包（10 类 × 20），生成编号/中英文名/分类/调色板（6 主色 + 4 情绪色 + 占比和）/`style_profile`/关键词/4 类模板行数/参考文件数/质量分级与问题清单；快照 **A 140、B 60、C 0**，重复主色调色板 0 组。
- 新增第 7 份契约 `packages/contracts/schemas/style-registry.schema.json`；构建报告 `docs/style-registry-report.md`（失效图链 59、目录名异常 8、manifest 旧绝对路径 79、缺来源说明 147）。
- 工具适配器 `packages/style_service/adapters.py`：8 工具结构契约 v1（06：mj/banana/sd；08：seedance_2_0/seedance_2_5/h3/runway/pika），`validate_prompt` 校验必填结构、必需/禁用标记、否定式、连续性禁令词、时长与运镜上限；`style_block` / `combined_prompt` 生成「【风格卡】七段 + 正文」。
- 风格服务 `registry.py` / `service.py`：按编号、中英文名、目录名解析注册表；`build_profile` 产出 `style-profile` 契约；`apply_profile` 写 `00_project/style-cards/style-<id>-profile.json` 并更新 `state.style`；`inject_prompt` 要求已 apply、按阶段限定工具白名单、只校验用户正文、写 `style-<id>-injection-<stage>-<tool>.json`（含正文 sha256 与组合提示词）。
- CLI 新增 `style list/show/resolve/validate/apply/inject`；`doctor` 增加风格注册表检查（共 7 项）；CLI 启动把 stdout/stderr 切到 UTF-8 容错（`errors="replace"`），提示词文件读取用 `utf-8-sig` 容忍 BOM。
- 新增 23 项测试（registry 4 / adapters 5 / service 9 / CLI 5），全量 141 项通过；本地 CI 全绿；品牌守卫 0 命中。
- Windows 实跑 E2E：真实项目 `悬疑短片PoC` → `style apply 001`（希区柯克）→ 06/mj 与 08/seedance_2_0 两次注入，记录与 `state.style` 一致。
- 文档：`docs/style-service.md`、`docs/iteration-3-report.md`；README/architecture/PRD 同步。

## [0.4.0] - 2026-11-14 — 迭代 1b：A 编排硬化

- 安装器 `packages/installer/`：`plan_install` / `install_skills`；同名旧 Skill 整体移入 `skills-backup-<时间戳>`，复制失败自动删除已装并恢复备份；升级时保留 `references/knowledge-base.json` / `knowledge-base.json` 原字节；支持 `--dry-run`。
- 初始化器 `core_router.project`：真实文档目录探测（Windows Shell 已知文件夹 / macOS 常见路径 / 环境变量覆盖），工作台配置（`~/.ai-film-workbench/config.json`），项目模板与状态卡 v2；`create_project` 生成 12 个项目目录、`state.json`、`brief.md`、`reference-memory.json`（`.md` 为人读视图）、`AGENTS.md`、`状态卡.md`。
- 状态卡 v2：`state.schema.json` 扩展知识桥、风格、确认文件、阶段产物、修订日志字段；`gates` 条目带阶段与更新时间。
- 门禁引擎 `core_router.gates`：注册表门禁 + 条件门禁（B 入口接管检查、知识桥开启后的知识卡确认）；硬门禁不可豁免；`advance` 在门禁未通过时拒绝并给出原因；上游修订按注册表顺序标记全部下游过期。
- 意图路由 `core_router.intent` + `content/intent-rules.json`：维护口令优先隔离（配置/更新知识库、整理新剧本、升级规则），其次知识库触发、修订、阶段、入口；修订优先于阶段识别。
- 参考记忆 v2：统一为 `00_project/reference-memory.json`（机器可读）+ `.md`（只读视图）；迁移器把旧「参考方法NNN」Markdown 条目转为契约条目，未知字段标注「迁移待核对」。
- 旧项目迁移 `migrate`：先备份到 `00_project/history/migrate-<时间戳>`，合并 brief/project-status/routing 字段为状态 v2，旧参考记忆改名为 `.legacy.md` 保留，写迁移报告，不改创作文件。
- 规则升级 `upgrade`：备份 `AGENTS.md` / `状态卡.md` / `routing.md` / `project-status.md`，补齐项目目录，按模板重写 `AGENTS.md`，刷新状态卡，写升级报告。
- CLI：新增 `route` / `gate`（list/pass/fail/waive）/ `next` / `install` / `migrate` / `upgrade`；`init` 改用初始化器，`doctor` 增加意图规则自检（共 6 项）；`check` 同时校验项目状态与参考记忆 JSON。
- 修正注册表 06→07 的默认推进关系（此前 06 会跳过 07）。
- 新增 50 项测试（gates 10 / intent 12 / project 12 / installer 7 / migrate 4 / E2E 5），全量 118 项通过；本地 CI 全绿。
- Windows 实跑 E2E：从零项目 01→02→04→05 推进（03 可选跳过）、门禁拦截、修订标记下游、旧项目迁移 + 规则升级。

## [0.3.1] - 2026-11-14 — 迭代 2.1：B 知识接入精度修订

- 证据质量评分：有效命中词数 + 结构语境词（情节/结局/身份/伏笔/结构/第三幕…）+2 + 常见叙事搭配（反转设计/身份反转/结局反转/核心事件…）+4 + 多词共现 +3；知识卡证据按评分降序（契约仍为 4 字段）。
- 动作/物件误命中过滤：「反转身」「反转过来」「反转过去」「反转方向」等模式内的命中不计入证据，并计入 `report.evidence_quality.filtered_mis_hits`。
- 置信策略：高置信证据（≥3 分）不少于 2 条时，丢弃纯字面低置信证据（计入 `low_confidence_dropped`）。
- 候选列表按证据最高分重排；报告新增 `evidence_quality`（considered/filtered_mis_hits/phrase_hits/cooccurrence_hits/top_score/high_confidence_evidence/low_confidence_dropped/sorted_by）。
- 新增 5 项测试，合计 68 项；覆盖质量排序、动作误命中过滤、短语/共现加权、低置信丢弃。
- 真实库实测（同查询）：8 条含噪声证据 → 2 条高置信证据（「身份反转设计」「核心事件：商战反转」），过滤动作误命中 3 条、丢弃低置信 3 条；知识库 SHA-256 与 mtime 不变。
- 更新文档：`docs/knowledge-service.md`（2.5 证据质量）、`docs/iteration-2-recall-report.md`（§8 精度修订实测）、`README.md`、`docs/architecture.md`。

## [0.3.0] - 2026-11-14 — 迭代 2：B 知识接入召回改进（方案 A）

- 元数据候选召回不足时，新增「有限正文回退」：按 lane 分类白名单 + 路径排除，在预算内逐份扫描 Markdown/TXT 正文并形成行级证据。
- 预算可配：`fallback_max_files`（默认 200）、`fallback_max_bytes`（单文件默认 256KB）；触发条件为证据不足或某个 lane 无候选；可用 `--no-fallback` 关闭。
- CLI 新增 `--no-fallback` / `--fallback-files` / `--fallback-bytes`；报告新增 `fallback`、`lane_candidates` 字段与文本输出行。
- 新增 4 项测试（adapter 1 + service 3），合计 63 项；覆盖预算上限、关闭开关、元数据未命中时的回退发现、lane/隔离边界。
- 真实库实测：仅 screenplay lane（元数据候选 0）→ 回退扫描 199 份，形成 8 条行级证据（05 剧本正文），知识库 SHA-256 与 mtime 不变；单次检索约 1 秒。
- 已知局限：回退为字面子串匹配，存在「反转身」等误命中；精度改进（多词共现/短语打分/词边界）留后续迭代。
- 新增文档：`docs/iteration-2-recall-report.md`；更新 `docs/knowledge-service.md`、`docs/architecture.md`。

## [0.2.0] - 2026-11-14 — 迭代 1a：B 知识服务 PoC

- 新增 `packages/knowledge_service/`：只读索引适配（`aistudio-md-2`）、行级证据链、知识卡组装与自校验。
- 新增 CLI：`knowledge probe` / `knowledge search`（知识卡写盘并可独立 `validate`）。
- 新增契约落地：知识卡（`knowledge-card` v1.0）在真实库实跑中通过 schema 校验。
- 新增 17 项测试（adapter 10 + service 7），覆盖只读、越界、无命中不编造、阶段→范围映射、CLI 退出码。
- 真实库验证：12,592 documents / 1,975 已索引正文；检索命中 4 条行级证据；检索前后知识库 SHA-256 与 mtime 不变。
- 新增文档：`docs/knowledge-service.md`、`docs/knowledge-poc-report.md`。
- 已知局限：现有 FTS5 表使用私有 tokenizer，外部不可复用；05/06 剧本召回率偏低，迭代 2 决策改进方案。

## [0.1.0] - 2026-11-14 — 迭代 0：地基

- 建立 `workbench` 开发仓库骨架与运行目录约定。
- 落地 contracts v1：`state` / `reference-memory` / `knowledge-card` / `style-profile` / `stage-artifact` / `stage-registry`。
- 落地 `stage-registry` v1（01–08 阶段 + 可选知识桥元数据，非阶段）。
- 落地 `brand-guard` v1：编码词表、变体归一化、白名单、表格文件扫描、CI 阻断。
- 落地 CLI 骨架：`version` / `doctor` / `check` / `brand-guard` / `init` / `validate`。
- 落地测试套件与本地 CI（`scripts/run_ci.py`）及 GitHub Actions 模板。
- 品牌基线：控制层与知识库说明文件零残留，语料人物名按例外保留。

## [0.0.1] - 2026-11-14

- 开发 PRD v0.1 评审草案。
