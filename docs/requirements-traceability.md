# 需求追溯表（FR ↔ 实现 ↔ 里程碑 ↔ 证据）

> 版本：2.21.0 · 状态：M34（迭代 37）落盘 · 维护规则见文末

本文件把 PRD §6 的 22 条功能需求（FR-01–FR-22）映射到工作台实现、里程碑与验证证据，作为需求—实现—验收之间的可审计链路。检查工具：`python scripts/check_fr_mapping.py`（CI 门禁，要求 22 条全覆盖、无重复）。

## 1. 主表：PRD 功能需求

| FR | 优先级 | 实现位置（模块/命令/契约） | 里程碑 | 证据 | 状态 |
|---|---|---|---|---|---|
| FR-01 统一安装器 | P0 | `packages/installer`（SKILL.md 源目录安装、备份/回滚/保留配置）+ CLI `install-skills` | 迭代 0 / 1b（0.4.0） | `docs/quick-start.md`、`docs/migration.md` | 已实现 |
| FR-02 工作台初始化器 | P0 | `workbench.py init`（文档目录探测、`00_project/` 初始化、入口/模式）+ `core_router.project.init_project` | 迭代 0 / 1b（0.4.0） | `docs/quick-start.md` | 已实现 |
| FR-03 阶段注册表 | P0 | `content/stage-registry.json` + `core_router.stage`（01–08 元数据、阶段路由） | 迭代 0（0.1.0） | `doctor` registry 检查、`tests/` | 已实现 |
| FR-04 意图路由 | P0 | `core_router.intent` + `content/intent-rules.json`（口令解析、维护口令） | 迭代 0（0.1.0）/ 1b（0.4.0） | `doctor` intent-rules 检查、`docs/command-card.md` | 已实现 |
| FR-05 门禁引擎 | P0 | `core_router.gates`（硬门禁不可豁免、断点确认、阶段推进） | 迭代 0（0.1.0） | `tests/`、`docs/flow-workbench.md` 确认断点 | 已实现 |
| FR-06 统一状态卡 v2 | P0 | `state.schema.json` v2 + `core_router.project`（load/save/refresh、迁移器） | 迭代 0 / 1b（0.4.0） | `doctor` contracts、`docs/migration.md` | 已实现 |
| FR-07 参考记忆 v2 | P0 | `core_router.memory` + `reference-memory.schema.json`（JSON 主存 + MD 视图） | 迭代 0 / 1b（0.4.0） | `tests/`、`00_project/reference-memory.json` | 已实现 |
| FR-08 知识库契约校验 | P0 | `knowledge_service` + `knowledge-card.schema.json`（只读适配 `knowledgeIndex.sqlite`） | 迭代 1a（0.2.0） | `docs/knowledge-service.md`、`tests/` | 已实现 |
| FR-09 检索与证据卡 | P0 | `knowledge_service` 候选人/证据、2/2.1 召回与精度修订 | 迭代 1a / 2 / 2.1（0.2.0–0.3.1） | `docs/knowledge-poc-report.md`、`docs/iteration-2-recall-report.md` | 已实现 |
| FR-10 索引维护 | P0 | `packages/knowledge_service/index_builder.py`（SQLite FTS5 trigram、分块、全量/增量、契约校验）+ CLI `index build/info/verify/search`；M22 `index_service.py` 接入知识服务（`search_index_card`、CLI `knowledge search --index`、flow 节点 `index` 参数） | M21（2.9.0）、M22（2.10.0） | `docs/knowledge-index.md`、`tests/test_knowledge_index.py`、`tests/test_knowledge_index_service.py` | 已实现（基础版，已接入服务） |
| FR-11 品牌守卫 | P0 | `brand_guard` + `config/brand-guard.json` + CI `brand-guard` 步骤 | 迭代 0（0.1.0） | CI 输出「命中 0 处」、`tests/` | 已实现 |
| FR-12 项目初始化与模板 | P0 | `workbench.py init`（内置项目模板 + 入口/模式引导）| 迭代 0 / 1b（0.4.0） | `docs/quick-start.md` | 已实现 |
| FR-13 版本与影响面 | P1 | `core_router.gates.mark_downstream_stale`（阶段变更影响提示） | 迭代 0（0.1.0） | `check --content` 下游过期提示 | 部分实现 |
| FR-14 风格注册表 | P1 | `content/style-registry.json` + `scripts/build_style_registry.py` | 迭代 3（0.5.0） | `docs/iteration-3-report.md`、`doctor` style-registry | 已实现 |
| FR-15 风格卡 | P1 | `style_service`（8 工具适配、build_profile/apply/inject） | 迭代 3（0.5.0） | `docs/iteration-3-report.md`、`tests/` | 已实现 |
| FR-16 06/08 挂载 | P1 | `style_service.inject` 到 06 提示词、08 交付集装配；`check --content` 校验 | 迭代 3 / 4（0.5.0–1.0.0） | `docs/pilot-c-report.md` | 部分实现 |
| FR-17 证据链与审计 | P1 | `00_project/workflows/runs/` 运行记录、`00_project/history/transactions.jsonl` 事务日志、生成任务回执 | 迭代 4 / M13–M18 | `flow replay/diff`、`flow batch-show` | 部分实现 |
| FR-18 导出与交付 | P1 | `workbench.py export/restore`（ZIP+元数据+路径校验）、`project artifacts-diff` | 迭代 4（1.0.0）/ M7 | `docs/migration.md`、`tests/` | 已实现 |
| FR-19 诊断与日志 | P1 | `workbench.py doctor`、`troubleshooting.md`、`scripts/bench.py`、daemon 日志轮转 | 迭代 0 / M16–M17 | CI 步骤、`docs/troubleshooting.md` | 已实现 |
| FR-20 文档体系 | P1 | `docs/`（quick-start/command-card/architecture/flow-workbench/migration/troubleshooting/release notes）+ `scripts/check_doc_links.py` | 迭代 0–M17 | CI doc-links 步骤 | 已实现 |
| FR-21 迁移与兼容 | P0 | `workbench.py migrate/upgrade`、契约 `contract_version`、快照与回滚（M18） | 迭代 1b（0.4.0）/ M18（2.6.0） | `docs/migration.md`、`docs/release-notes-2.6.0.md` | 已实现 |
| FR-22 测试与发布自动化 | P0 | `scripts/run_ci.py`（九步门禁，含行覆盖≥80%/分支覆盖≥50%与可复现构建）、`build_manifest.py`、`build_release.py`、`package_smoke.py`、`rollback_drill.py` | 迭代 0–M19 | CI 日志、`dist/` 发行包与 SHA256 | 已实现 |

## 2. 扩展能力（PRD 迭代记录中的工作台能力，非 §6 基础 FR）

| 能力 | 里程碑 | 主要实现 | 关联 FR |
|---|---|---|---|
| 可视化节点工作台（17 类节点/模板/运行历史） | M1–M8（1.1.0–1.7.0） | `packages/flow`、`packages/webui`、5 份 flow 契约 | FR-05、FR-18 |
| 生成平台适配（4 provider/任务记录/状态轮询/回填/重试） | M8–M11（1.7.0–1.10.0） | `packages/generate`、`generate-*` 契约 | FR-17、FR-18 |
| 批次编排/并行预演/失败恢复 | M12–M13（2.0.0–2.1.0） | `packages/flow/batch.py`、`flow-batch` 契约 | FR-17、FR-18 |
| 队列/定时/取消重排/守护/重试/通知 | M14–M16（2.2.0–2.4.0） | `packages/flow/queue.py`、`flow-queue` 契约 | FR-17、FR-19 |
| 实时预览与界面迭代 | 2.0.1 | `/api/dev/version`、节点分类视觉、17 类演示图 | FR-19、FR-20 |
| PRD 验收工具链/NFR 基准 | M17（2.5.0） | `check_doc_links.py`、`package_smoke.py`、`bench.py` | FR-20、FR-22 |
| 项目状态快照与回滚/发行包回滚演练 | M18（2.6.0） | `core_router/rollback.py`、`rollback_drill.py` | FR-21、FR-22 |
| 检索配置与查询扩展 | M27（2.14.0） | `knowledge-search` 契约、`content/knowledge-search.json`、`packages/knowledge_service/index_builder.py::load_search_config/search_index`、CLI `index search --config/--weights`、`tests/test_knowledge_search_config.py` | FR-10、FR-12 |
| 队列运维增强（cron/批次 webhook/批次历史） | M28（2.15.0） | `packages/flow/cron.py`、`packages/flow/notify.py`、`flow queue daemon --cron`、`flow batch --webhook-url`、Web `loadBatches` 面板、`tests/test_flow_cron.py`、`tests/test_flow_batch_webhook.py` | FR-17、FR-19、FR-22 |
| 索引健康巡检与同义词权重 | M29（2.16.0） | `packages/knowledge_service/index_health.py::check_health`、CLI `index health`、`knowledge-search` 可选 `synonym_weight`、`tests/test_index_health.py`、`tests/test_knowledge_search_config.py` | FR-10、FR-12 |
| 检索结果精细化 | M30（2.17.0） | `knowledge-search` 可选 `min_score`/`max_per_file`/`snippet_chars`/`proximity_weight`、`index_builder._proximity_score`/`_apply_result_limits`、CLI `index search --min-score/--max-per-file`、`tests/test_knowledge_search_config.py`（SearchLimitsTest 9 项） | FR-10、FR-12 |
| 批次/队列运维收尾（cron 预览/批次趋势/失败告警聚合） | M31（2.18.0） | `flow/queue.py::summarize_notifications`、CLI `flow cron-preview`/`flow queue alerts`、Web `POST /api/cron/preview`/`GET /api/queue/alerts`、`tests/test_flow_queue.py::NotificationSummaryTest`、`tests/test_webui_api.py`（M31 两项） | FR-17、FR-19 |
| 队列告警运维闭环（告警摘要外送/巡检退出码/一键恢复） | M32（2.19.0） | `packages/flow/queue.py::push_queue_alerts`；CLI `flow queue alerts --webhook-url/--fail-if-failures`；`app.js::recoverAllFailedBatches`；`tests/test_flow_queue.py::AlertsDigestTest`、`tests/test_cli_coverage.py::test_m32_alerts_push_and_exit` |
| 告警外送增强与批次趋势报表（webhook 重试/飞书格式/报表导出） | M33（2.20.0） | `packages/flow/notify.py`（`build_webhook_body`、`notify_webhook` retries）、`packages/flow/report.py::batch_report`；CLI `flow batch-report`、`--webhook-format/--webhook-retries`；`tests/test_flow_notify.py`、`tests/test_flow_report.py` |
| 批次报表 Web 化与告警静默窗口（报表预览/导出、告警去重） | M34（2.21.0） | `packages/webui/server.py`（`GET /api/batches/report`）、`packages/webui/static/app.js`（报表 MD/CSV/预览按钮）、`packages/flow/queue.py::push_queue_alerts`（`dedupe_minutes`）、CLI `flow queue alerts --dedupe-minutes`；`tests/test_webui_api.py`、`tests/test_flow_queue.py` |
| 远端 CI 工作流硬化与就绪检查 | M26（2.13.1） | `.github/workflows/ci.yml`（permissions/concurrency/timeout/UTF-8）、`scripts/ci_ready.py`、`docs/github-actions.md`、`tests/test_ci_ready.py` | FR-21、FR-22 |
| 分支覆盖率门禁 | M25（2.13.0） | `scripts/coverage_check.py --branches`（`dis` 静态分支点 + 局部 `sys.monitoring` BRANCH 事件）、`scripts/run_ci.py` 覆盖率步骤、`tests/test_ci_scripts.py::BranchCoverageTest` | FR-22（NFR） |
| 索引混合排序与队列 webhook 通知 | M24（2.12.0） | `packages/knowledge_service/index_builder.py::search_index(mode)`、`knowledge_service/index_service.py`（hybrid 排序）、`packages/flow/queue.py::_notify_webhook`、CLI `index search --mode`/`queue run --webhook-url`、`tests/test_knowledge_index.py::HybridSearchTest`、`tests/test_flow_queue.py::FlowQueueWebhookTest` | FR-10、FR-17、FR-19 |
| 覆盖率提升与 80% 门禁 | M23（2.11.0） | `tests/test_cli_coverage.py`、`tests/test_webui_api.py::test_http_error_paths`、`scripts/coverage_check.py --min 80`、`scripts/run_ci.py` | FR-22（NFR） |
| 索引证据卡接入知识服务 | M22（2.10.0） | `packages/knowledge_service/index_service.py`、CLI `knowledge search --index`、flow `knowledge_search` 节点 `index` 参数、`tests/test_knowledge_index_service.py` | FR-10、FR-12、FR-13 |
| 知识库索引维护（重建/增量/FTS5 检索） | M21（2.9.0） | `packages/knowledge_service/index_builder.py`、`knowledge-index` 契约、`index` CLI | FR-10、FR-17 |
| 跨平台 CI/覆盖率/可复现构建/快照回滚 Web | M20（2.8.0） | `scripts/coverage_check.py`、`scripts/repro_check.py`、`.github/workflows/ci.yml`、`/api/rollback/*` | FR-19、FR-21、FR-22 |

## 3. 维护规则

- 新增/修改 PRD §6 的 FR 后，必须同步更新本表，并在同迭代 PRD §9.x 记录中登记；CI 的运行 `check_fr_mapping.py` 会校验覆盖与重复。
- 状态口径：`已实现`（主路径可用且有测试/证据）、`部分实现`（主路径可用但缺口见备注）、`未实现`（P0/P1 缺口，应在后续里程碑或风险表登记）。
- 证据列优先填可复现命令/文档路径，不在表中大面积复制测试代码。

## 4. 检查

```bash
python scripts/check_fr_mapping.py            # 校验 22 条 FR 全覆盖、无重复
python scripts/check_fr_mapping.py --json     # 机器可读报告
```
