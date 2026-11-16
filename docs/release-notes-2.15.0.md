# workbench 2.15.0 发行说明（M28 队列运维增强）

日期：2026-11-16 · 版本：2.15.0（MINOR，向后兼容） · 契约：contracts v1.0（17 份，无变更）

## 能力

1. **cron 定时队列守护**
   - `flow queue daemon --cron "*/5 * * * *"`：五段式（分 时 日 月 周），支持 `*`、`*/n`、`a-b`、`a-b/n`、逗号列表；日+周同时受限时按 OR。
   - 按分钟匹配触发，记录 last fired 防止同一分钟重复执行；非法表达式退出 2 并给出字段级错误；保留 `--interval` 轮询模式。
2. **批次失败 webhook**
   - `flow batch --webhook-url <URL>`：批次有失败图时把 `{at,event:"batch.run",project,batch_id,status,message,failed_graphs,summary}` JSON POST 到 webhook。
   - 外送失败不阻断批次（结果记录在返回的 `webhook` 字段）；未配置 `--webhook-url` 为 no-op。webhook 实现抽到公共 `flow/notify.py`，队列与批次共用。
3. **Web 批次历史面板**
   - 运行面板下方展示最近 10 个批次（状态、成功/失败、耗时、并行线程数）；失败批次可点「恢复失败图」调用 `POST /api/batches/<batch_id>/recover` 并刷新。

## 验证

- 全量 `Ran 470 tests ... OK`；新增 11 项（cron 8、批次 webhook 3）。
- 行覆盖率 80.9%（6556/8104）、分支覆盖率 51.0%（3053/5986），CI 双门槛通过。
- 九步 CI 全绿（编译/文档链接/FR 映射/测试/覆盖率/doctor/冷启动基准/品牌守卫/可复现构建）。
- CLI 冒烟：非法 cron 退出 2 并提示五段格式；`flow batch --webhook-url` 输出 webhook 结果（HTTP 状态码或错误原因），失败不影响批次记录。

## 使用

```bash
python workbench.py flow queue daemon --project 我的短片 --cron "*/5 * * * *" --all-projects
python workbench.py flow batch --project 我的短片 --all --live --webhook-url http://localhost:9000/hook
```

## 限制

- cron 为分钟粒度，不支持秒级与时区偏移（使用本机时区）。
- webhook 只在批次失败时外送，超时 10 秒；未配置不重试。
- Web 批次历史面板只展示最近 10 条、不自动轮询；恢复操作依赖既有批次恢复端点。
- 与 2.14.0 兼容：无契约变更、无破坏性 CLI/API 变化。
