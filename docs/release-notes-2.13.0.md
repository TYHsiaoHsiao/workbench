# 2.13.0 发行说明（M25：分支覆盖率门禁）

## 能力

- `scripts/coverage_check.py` 支持 `--branches` / `--min-branches`：`dis` 静态收集 if/while/for/and/or 分支点，测试前导入 `packages` 模块并对其 code 对象注册局部 `sys.monitoring` BRANCH 事件；JSON 同时输出 line 与 branch。
- `scripts/run_ci.py` 覆盖率步骤：`--min 80 --branches --min-branches 50`。
- `tests/test_ci_scripts.py` 新增 5 项测试（分支点收集、双向记录、汇总数学、模块登记、外部路径显示）。

## 验证

- 行覆盖 **80.84%（6374/7885）**；分支覆盖 **50.52%（2914/5768）**；全量 **434 项测试**。
- CI 九步全绿（doc-links/fr-mapping/tests/coverage/doctor/bench/brand-guard/repro）。
- 发行包与回滚演练见 CI 产物。

## 限制

- 分支口径只覆盖可导入 `packages` 模块的代码对象（模块顶层/运行期动态代码不计入分母）。
- 分支测量使覆盖率步骤耗时约 65s → 230s。
- 分支门槛 50% 为当前基线；新增分支必须带测试。

## 兼容性

- 行覆盖率口径与 80% 门禁不变；`coverage_check.py` 默认不启用分支，需显式 `--branches`。
