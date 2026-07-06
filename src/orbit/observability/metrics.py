"""Prometheus 业务指标 (Step 7.2 AgentOps).

WHY 补充 prometheus-fastapi-instrumentator:
Instrumentator 只提供 HTTP 层指标 (请求数/延迟/状态码),
不覆盖调度器/LLM/防幻觉/沙箱等业务指标。
本模块定义这些业务指标, 各组件调用 .inc()/.observe()/.set() 埋点。

命名规范: orbit_<component>_<metric>_<unit>
- Counter 后缀 _total (Prometheus 惯例, 自动追加)
- Histogram 后缀 _seconds (时间单位)
- Gauge 无后缀
"""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter, Gauge, Histogram

# ---- 任务指标 --------------------------------------------------

orbit_tasks_total = Counter(
    "orbit_tasks_total",
    "任务总数 (按状态)",
    ["status"],  # success | failed | timeout | cancelled
)

orbit_task_duration_seconds = Histogram(
    "orbit_task_duration_seconds",
    "任务执行耗时",
    ["agent_role"],  # architect | coder | reviewer | tester | devops
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120],
)

orbit_active_tasks = Gauge(
    "orbit_active_tasks",
    "当前活跃任务数",
)

# ---- LLM 指标 --------------------------------------------------

orbit_llm_tokens_total = Counter(
    "orbit_llm_tokens_total",
    "LLM Token 消耗",
    ["type"],  # input | output
)

orbit_llm_call_duration_seconds = Histogram(
    "orbit_llm_call_duration_seconds",
    "LLM 调用耗时",
    ["model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
)

# ---- 防幻觉指标 -------------------------------------------------

orbit_hallucination_intercepted_total = Counter(
    "orbit_hallucination_intercepted_total",
    "防幻觉拦截次数 (按层)",
    ["layer"],  # L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9
)

orbit_hallucination_entropy_gauge = Gauge(
    "orbit_hallucination_entropy_gauge",
    "LLM 输出熵值 (最近一次)",
)

# Charter SLA: 幻觉率 < 3%——验证层误判/总验证次数
# label `pass` 记录通过（代码被验证层放行），`flag` 记录拦截。
# 幻觉率 = flag / (pass + flag)，需人工审查 flag 中的 false_positive 率
orbit_hallucination_validations_total = Counter(
    "orbit_hallucination_validations_total",
    "防幻觉验证次数 (Charter SLA 指标)",
    ["result"],  # pass | flag
)

# ---- 调度器指标 (Charter SLA) -----------------------------------

orbit_scheduling_latency_seconds = Histogram(
    "orbit_scheduling_latency_seconds",
    "调度层延迟 (Charter SLA: <=1500ms)",
    ["operation"],  # run_dag | execute_layer | dispatch_task | resume_dag
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 5.0],
)

# ---- 熔断器指标 -------------------------------------------------

orbit_circuit_breaker_state = Gauge(
    "orbit_circuit_breaker_state",
    "熔断器状态 (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["breaker"],  # z3 | sandbox | llm
)

# ---- 沙箱指标 --------------------------------------------------

orbit_sandbox_pool_available = Gauge(
    "orbit_sandbox_pool_available",
    "沙箱池可用实例数",
)
# -1 = 未初始化 (MVP 阶段无沙箱池), 避免误触发 sandbox_pool_exhausted 告警
orbit_sandbox_pool_available.set(-1)

orbit_sandbox_executions_total = Counter(
    "orbit_sandbox_executions_total",
    "沙箱执行总数 (按结果)",
    ["result"],  # success | failed | timeout
)

# ---- 合规指标 --------------------------------------------------

orbit_compliance_checks_total = Counter(
    "orbit_compliance_checks_total",
    "合规检查总数 (按结果)",
    ["status"],  # pass | warning | violation
)

# ---- 知识图谱指标 -----------------------------------------------

orbit_knowledge_queries_total = Counter(
    "orbit_knowledge_queries_total",
    "知识查询总数 (按模式)",
    ["mode"],  # exact | semantic | hybrid
)


def record_hallucination_validation(passed: bool) -> None:
    """记录防幻觉验证结果——用于 Charter SLA 幻觉率计算。

    在验证层判定后调用：L4/L5/L6/L7 validate() 返回时，
    passed=True → `pass`（放行），passed=False → `flag`（拦截）。
    SLA 幻觉率 = flag / (pass + flag)。
    """
    orbit_hallucination_validations_total.labels(
        result="pass" if passed else "flag"
    ).inc()


def record_scheduling_latency(operation: str, duration_seconds: float) -> None:
    """记录调度延迟——用于 Charter SLA 调度延迟指标。

    operation: run_dag | execute_layer | dispatch_task | resume_dag
    duration_seconds: 操作耗时（秒）

    WHY Histogram: 查看 P50/P95/P99 延迟分布，判断是否超 1500ms 阈值。
    """
    orbit_scheduling_latency_seconds.labels(operation=operation).observe(duration_seconds)


def snapshot() -> dict[str, Any]:
    """采集当前所有指标快照——供 REST API 和 WS 推送。

    WHY 返回 dict 而非 Prometheus 文本格式:
    REST/WS 消费方是前端, JSON 可直接渲染。
    """
    return {
        "tasks_total": {
            "success": _counter_value(orbit_tasks_total, {"status": "success"}),
            "failed": _counter_value(orbit_tasks_total, {"status": "failed"}),
            "timeout": _counter_value(orbit_tasks_total, {"status": "timeout"}),
        },
        "active_tasks": orbit_active_tasks._value.get(),
        "llm_tokens_total": {
            "input": _counter_value(orbit_llm_tokens_total, {"type": "input"}),
            "output": _counter_value(orbit_llm_tokens_total, {"type": "output"}),
        },
        "hallucination_intercepted_total": {
            layer: _counter_value(orbit_hallucination_intercepted_total, {"layer": layer})
            for layer in ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"]
        },
        # Charter SLA 指标
        "sla_scheduling_latency": {
            "run_dag": _histogram_avg(orbit_scheduling_latency_seconds, {"operation": "run_dag"}),
            "dispatch_task": _histogram_avg(orbit_scheduling_latency_seconds, {"operation": "dispatch_task"}),
        },
        "sla_hallucination_rate": {
            "pass": _counter_value(orbit_hallucination_validations_total, {"result": "pass"}),
            "flag": _counter_value(orbit_hallucination_validations_total, {"result": "flag"}),
        },
        "circuit_breaker_state": {
            "z3": orbit_circuit_breaker_state.labels(breaker="z3")._value.get(),
            "sandbox": orbit_circuit_breaker_state.labels(breaker="sandbox")._value.get(),
            "llm": orbit_circuit_breaker_state.labels(breaker="llm")._value.get(),
            "resource_guard": orbit_circuit_breaker_state.labels(
                breaker="resource_guard"
            )._value.get(),
        },
        "sandbox_pool_available": orbit_sandbox_pool_available._value.get(),
        "sandbox_executions_total": {
            "success": _counter_value(orbit_sandbox_executions_total, {"result": "success"}),
            "failed": _counter_value(orbit_sandbox_executions_total, {"result": "failed"}),
        },
        "compliance_checks_total": {
            "pass": _counter_value(orbit_compliance_checks_total, {"status": "pass"}),
            "warning": _counter_value(orbit_compliance_checks_total, {"status": "warning"}),
            "violation": _counter_value(orbit_compliance_checks_total, {"status": "violation"}),
        },
    }


def _histogram_avg(histogram: Histogram, labels: dict[str, str]) -> float:
    """读取 Histogram 的平均值（最近观测窗口）。

    Prometheus Histogram 有 _sum 和 _count，平均值 = _sum / max(_count, 1)。
    """
    try:
        c = histogram.labels(**labels)
        total: float = float(c._sum.get())
        count: float = float(c._count.get())
        if count < 1:
            return 0.0
        return round(total / count, 5)
    except (KeyError, AttributeError):
        return 0.0


def _counter_value(counter: Counter, labels: dict[str, str]) -> float:
    """安全读取 Counter 带 label 的值。

    Prometheus client 无 label 时不返回 0 而是 KeyError,
    本函数兜底返回 0.0。
    """
    try:
        val: Any = counter.labels(**labels)._value.get()
        return float(val)
    except KeyError:
        return 0.0
