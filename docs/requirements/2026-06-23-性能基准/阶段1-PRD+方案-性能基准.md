# Step 6.3 性能基准 — PRD+技术方案（合并）

> 范围小，PRD+方案合并。基线：Step 6.2 E2E 测试框架 + PRD+ADR Q2 阈值。

## 1. 背景

Step 6.2 已交付 10 个 E2E 用例（正常/重试/熔断/WS/API），但缺系统性能基线。不知道单任务 P95 延迟、不知道并发瓶颈。需要一个轻量性能基准套件，复用 E2E fixture。

## 2. 用户故事

| # | 作为 | 我希望 | 以便 | P |
|---|---|---|---|---|
| US1 | 开发者 | 每次 commit 自动跑性能基准 | 发现引入性能回退的改动 | P0 |
| US2 | 技术负责人 | PR 页面看到 P50/P95 指标 | 合并前评估性能影响 | P1 |

## 3. 功能需求

### 3.1 性能测试（pytest-benchmark）

| 测试 | 内容 | 指标 |
|------|------|------|
| 单任务 E2E 全链路 | 创建→调度→DONE（Mock LLM） | P50/P95/P99 延迟 |
| 并发 3 任务 | asyncio.gather 3 个 run_task | P95 延迟 |
| EventBus 吞吐 | publish→subscribe 1000 事件 | 事件/秒 |
| WS 推送延迟 | publish → WS 客户端收到 | 端到端延迟 ms |

### 3.2 阈值

| 指标 | CI 阈值 | 动作 |
|------|---------|------|
| 单任务 P50 | <3s | 超过 → 标记 warning |
| 单任务 P95 | <12s（CI）/ <8s（预发布） | 超过 → 标记 warning |
| 并发 3 任务 P95 | <20s | 超过 → 标记 warning |
| EventBus 吞吐 | >5000 events/s | 低于 → 标记 warning |

> 全部非阻塞——性能回归记 warning 不阻断 merge（PRD+ADR Q2）。

### 3.3 CI 集成

```yaml
# .github/workflows/perf.yml（新增）
- name: Performance benchmark
  run: poetry run pytest tests/perf/ -v --benchmark-only --benchmark-json=perf.json
- name: Check thresholds
  run: python scripts/check_perf_thresholds.py perf.json
```

## 4. 边缘情况

| 场景 | 行为 |
|------|------|
| CI runner 性能波动 | 过去 5 次均值的 ±30% 不告警 |
| Docker 不可用 | skip（与 E2E 一致） |
| 首次运行无基线 | 建立基线不告警 |

## 5. 影响范围

```
tests/perf/
├── __init__.py
├── conftest.py           # 复用 tests/e2e/conftest.py 的 fixture
├── test_perf_single.py   # 单任务性能
├── test_perf_concurrent.py # 并发性能
└── test_perf_eventbus.py # EventBus 吞吐

.github/workflows/perf.yml

scripts/
└── check_perf_thresholds.py
```

依赖：`pytest-benchmark`（poetry add --group dev）。

## 6. 验收标准

| # | 标准 |
|---|---|
| AC1 | `pytest tests/perf/ --benchmark-only` 4 测试全通过 |
| AC2 | CI perf job 正常运行（绿色或黄色 warning） |
| AC3 | 性能报告 JSON 可解析 |
| AC4 | 阈值脚本输出可读（哪个指标超标/达标） |

## 7. Non-Goals

- Locust 分布式压测（MVP 过重）
- 真实 LLM 性能测试（Mock LLM 足够）
- 性能回归自动阻断 merge（V2）

---

> 阶段1+阶段2 合并完成。确认后直接进阶段3编码。
