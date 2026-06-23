# PRD+ADR_Step7.3：ResourceGuard 熔断器

## Step 7.3：ResourceGuard 熔断器

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | LLM API 调用的 Token 消耗和响应延迟存在显著波动，单任务 Token 超过预期会直接导致用户费用超支；连续失败或超时会影响系统可用性。Phase 0-6 的各层防御（防幻觉、验证器、沙箱）无法保护系统免受"资源耗尽"类故障的影响，需要独立的熔断保护层。 |
| **用户故事** | 作为 V14.1 系统，当 LLM API 调用超出预算（Token 超过阈值）或响应超时时，我应自动触发熔断机制，阻止资源继续消耗，并切换到降级路径，确保系统整体可用性。 |
| **需求描述** | ① **自研熔断器**：令牌桶 + 滑动窗口混合计数器，实现 CLOSED / OPEN / HALF_OPEN 三态转换。<br>② **熔断条件**：连续 5 次失败 **或** 错误率 >30% **或** 单任务 Token 超过预算 × 1.5。<br>③ **决策延迟**：allow_request() 延迟 ≤12ms（纯内存判断，无 IO）。<br>④ **多级降级链路**：L1→切换备用模型（DeepSeek→Qwen-Coder）；L2→本地规则引擎；L3→缓存数据（标记"陈旧"）；L4→转人工挂起。<br>⑤ **恢复机制**：半开状态每 5 分钟允许限量试探请求，成功率 >50% 则恢复正常。<br>⑥ **审计集成**：每次熔断事件记录到 `task_audit_trail`（含触发原因、当前状态、降级路径）。 |
| **范围 (Do/Don't)** | **Do：** Token 预算熔断；API 失败熔断；多级降级链路；半开恢复。<br>**Don't：** 不替代负载均衡（那是网关层职责）；不自动扩缩容（那是 K8s HPA 职责）。 |
| **数据契约** | **CircuitBreakerState:** `{"state": "CLOSED\|OPEN\|HALF_OPEN", "failure_count": int, "last_failure_time": float, "success_in_half_open": int}`<br>**熔断事件:** `{"event": "CIRCUIT_OPEN", "trigger": "TOKEN_EXCEEDED\|API_FAILURE\|ERROR_RATE", "task_id": str, "timestamp": float, "degradation_path": str}` |
| **异常定义** | ① **外部 API 全挂**：连续熔断次数 >10 → 发送 CRITICAL 告警到 AlertManager，通知运维人工介入。<br>② **Token 超限但 API 正常** → 仅阻断当前任务，不触发全局熔断。<br>③ **熔断状态持久化失败** → 降级为内存状态（重启后状态丢失但服务不崩溃）。 |
| **成功标准→验收** | **SC1:** 熔断决策延迟 ≤12ms → **AC1:** 基准测试 `allow_request()` P99 <12ms（10000次调用）。<br>**SC2:** 熔断触发准确率 ≥95% → **AC2:** 对 100 个已知超限场景（50 个 Token 超限 + 50 个 API 失败），正确触发 ≥95 次。<br>**SC3:** 降级路径可切换 → **AC3:** 每级降级路径可独立验证，降级后任务成功率 ≥80%。 |
| **待定决策** | **Q:** 半开试探请求数量是多少？ → **决议：** 默认 3 个/分钟，避免在半开状态下对 API 造成压力。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **决策** | 采用令牌桶 + 滑动窗口混合计数器，而非简单计数器或固定窗口计数器。 |
| **理由** | 1. **令牌桶**允许突发流量（某时段 Token 消耗较高但整体未超），避免误断。<br>2. **滑动窗口**平滑短期波动（3 分钟内错误率），避免瞬时抖动误触。<br>3. **决策纯内存**，无 IO 延迟，≤12ms 可保证不阻塞调度器主循环。<br>4. 无需外部依赖库，纯 Python asyncio 实现，轻量可控。 |
| **技术栈** | Python 3.11+ asyncio；无外部依赖（自研轻量实现）；Redis 可选（分布式部署时共享熔断状态）。 |
| **架构位置** | 调度器与 LLM API 之间，所有 LLM 调用必经之路，是资源预算的守门员。 |
| **实施细节** | **CLOSED 状态：** 计数器记录连续失败数和滑动窗口内错误率，允许所有请求通过。<br>**OPEN 状态：** 所有 LLM 请求直接返回降级响应，冷却计时器启动（默认 60s）。<br>**HALF_OPEN 状态：** 允许限量试探请求（3 个/分钟），根据成功率决定转到 CLOSED 或回 OPEN。<br>**Token 预算追踪：** 每个任务维护独立计数器，超限时触发局部熔断（不影响其他任务）。 |
| **风险与缓解** | 风险：熔断器本身成为单点故障。缓解：熔断器异常时默认放行请求（fail-open），保证服务可用。<br>风险：降级链路不work。缓解：每级降级路径有独立健康检查，降级失败时自动跳到下一级。 |
| **依赖链** | 前置：无（独立模块）。<br>依赖：Step 5.6（资源调度器统一配额管理）；Step 11（Token 监控基础）。<br>被依赖：Step 5.1（调度器状态机）；Step 14.3（降级与容错策略）。 |

---

### ✅ 验收测试 · pytest

```python
import pytest
from src.circuit_breaker import ResourceGuard, CircuitState

class TestStep73ResourceGuard:
    """Step 7.3 ResourceGuard 熔断器 — 验收测试"""

    def test_circuit_breaker_state_transitions(self):
        """CLOSED → OPEN → HALF_OPEN → CLOSED 状态转换正确"""
        guard = ResourceGuard(failure_threshold=5)
        # 模拟5次失败
        for _ in range(5):
            result = guard.record_failure()
        assert guard.state == CircuitState.OPEN
        # 等待冷却后进入 HALF_OPEN
        guard.force_cool_down()
        assert guard.state == CircuitState.HALF_OPEN
        # 模拟试探成功
        guard.record_success()
        assert guard.state == CircuitState.CLOSED

    def test_decision_latency(self):
        """SC1: allow_request() P99 <12ms"""
        guard = ResourceGuard()
        latencies = []
        for _ in range(10000):
            start = pytest.perf_counter()
            guard.allow_request(task_id="test")
            latencies.append((pytest.perf_counter() - start) * 1000)
        latencies.sort()
        p99 = latencies[9900]
        assert p99 < 12, f"P99 latency {p99:.2f}ms exceeds 12ms"

    def test_circuit_breaker_accuracy(self):
        """SC2: 熔断触发准确率 ≥95%"""
        guard = ResourceGuard(failure_threshold=5, token_budget_multiplier=1.5)
        correct_triggers = 0
        # 50个 Token 超限场景
        for i in range(50):
            if guard.should_trip_on_token_exceeded(task_id=f"t{i}", tokens=100000, budget=50000):
                correct_triggers += 1
        # 50个 API 失败场景
        for i in range(50):
            for _ in range(5):
                guard.record_failure()
            if guard.state == CircuitState.OPEN:
                correct_triggers += 1
            guard.reset()
        accuracy = correct_triggers / 100
        assert accuracy >= 0.95, f"Accuracy {accuracy:.2%} below 95%"

    def test_graceful_degradation(self):
        """SC3: 多级降级路径可切换"""
        guard = ResourceGuard()
        paths = []
        # L1: 备用模型
        result = guard.get_degraded_response(degradation_level=1)
        paths.append(result["path"] == "L1_BACKUP_MODEL")
        # L2: 规则引擎
        result = guard.get_degraded_response(degradation_level=2)
        paths.append(result["path"] == "L2_RULE_ENGINE")
        # L3: 缓存
        result = guard.get_degraded_response(degradation_level=3)
        paths.append(result["path"] == "L3_STALE_CACHE")
        assert all(paths), "Some degradation paths failed"

    def test_half_open_recovery(self):
        """半开状态试探请求机制"""
        guard = ResourceGuard()
        # 强制进入 OPEN
        for _ in range(5):
            guard.record_failure()
        guard.force_cool_down()
        assert guard.state == CircuitState.HALF_OPEN
        # 3个试探请求
        for _ in range(3):
            guard.record_success()
        assert guard.state == CircuitState.CLOSED

    def test_audit_integration(self):
        """熔断事件记录到 task_audit_trail"""
        guard = ResourceGuard()
        for _ in range(5):
            guard.record_failure()
        # 验证审计事件已记录
        events = guard.get_audit_events()
        assert len(events) >= 1
        assert events[-1]["event"] == "CIRCUIT_OPEN"
        assert "trigger" in events[-1]
```
