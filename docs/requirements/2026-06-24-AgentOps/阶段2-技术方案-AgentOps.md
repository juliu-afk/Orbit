# 阶段2 技术方案——完整 AgentOps 体系

> 基于阶段1 PRD `docs/PRD+ADR_AgentOps体系.md`（验收标准 5 条），本次技术方案覆盖 5 条，无偏离。

## 需求回顾（PRD 验收标准）

| # | 验收标准 | 本次覆盖 |
|---|---------|---------|
| AC1 | 8 核心组件埋点覆盖率 100%，审计日志完整性 ≥95% | ✅ P0 |
| AC2 | 告警准确率 ≥90%（人工评审 100 条，真实 ≥90） | ✅ P0 规则引擎 |
| AC3 | 仪表盘加载 P99 <3s | ✅ P1 Grafana JSON 模板 |
| AC4 | 追踪链：请求→响应完整调用链可查询 | ⚠️ P2（需 OTel Collector+Tempo 基础设施，出配置模板） |
| AC5 | 驾驶舱 WebSocket 实时推送运维数据 | ✅ P0 EventBus 事件 |

## 分层策略

| 层 | 内容 | 本次 | 理由 |
|---|---|---|---|
| P0 代码层 | 结构化日志增强 + Prometheus 自定义指标 + 审计日志 + 反馈闭环 + 规则引擎告警 + WS 事件推送 | ✅ 实现 | 仅用已有依赖，零新 dep |
| P1 配置层 | AlertManager 规则 + Grafana Dashboard JSON | ✅ 静态配置 | 供生产部署引用 |
| P2 基础设施层 | OTel Collector + Tempo + ELK + K8s Helm | 仅出配置模板 | 需 K8s 集群，不出实际部署 |

### OpenTelemetry 决策

**不在 P0 引入 OpenTelemetry SDK。** 理由：
1. 需新增 `opentelemetry-api` + `opentelemetry-sdk` + `opentelemetry-exporter-otlp` 三个包，违反"新依赖先问"规则
2. OTel 的价值在 Collector → Tempo/Jaeger 链路，无后端基础设施时只是往 stdout 打 span——structlog + trace_id 手动关联已覆盖同等可观测性
3. structlog 已支持 `trace_id` 绑定，配合 Prometheus metrics 的 `task_id` label，足以在 MVP 阶段定位问题

**后续升级路径**：基础设施就绪后，添加 `opentelemetry-instrumentation-fastapi` 一行即可自动注入 trace context，无需改业务代码。

## 影响范围

### 新增文件

| 文件 | 职责 |
|------|------|
| `src/orbit/observability/metrics.py` | Prometheus 自定义指标（Counter/Gauge/Histogram） |
| `src/orbit/observability/audit.py` | 审计日志记录器 + 教训库（SQLite） |
| `src/orbit/observability/alerts.py` | 告警规则引擎（阈值检测 + 状态机） |
| `src/orbit/observability/config.py` | AgentOps 配置（阈值、开关） |
| `configs/alertmanager/rules.yml` | AlertManager 告警规则（P1 模板） |
| `configs/grafana/dashboards/agentops-overview.json` | Grafana 仪表盘（P1 模板） |
| `configs/otel/otel-collector-config.yml` | OTel Collector 配置（P2 模板） |
| `configs/logstash/pipeline.conf` | Logstash 审计日志管道（P2 模板） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/orbit/observability/__init__.py` | 导出新模块 |
| `src/orbit/observability/collector.py` | 集成 metrics 埋点 |
| `src/orbit/api/routes/observability.py` | 新增 `/metrics/business` + `/audit` + `/alerts` 端点 |
| `src/orbit/events/schemas.py` | 新增 `MetricsEvent` + `AlertEvent` 事件类型 |
| `src/orbit/core/config.py` | 新增 AgentOps 相关配置项 |
| `tests/unit/test_observability.py` | 扩展测试（9→25+） |

## 架构设计

### 模块关系图

```
┌─────────────────────────────────────────────────────────┐
│                    observability/                        │
│                                                         │
│  config.py          metrics.py          alerts.py        │
│  AgentOpsConfig     Prometheus 指标     告警规则引擎      │
│  (阈值/开关)        Counter/Gauge/      (内存状态机)       │
│                     Histogram                            │
│  collector.py       ┌──────────────────────────┐        │
│  HealthCollector    │  audit.py                          │
│  (已有,集成metrics)  │  AuditLogger + LessonStore(SQLite) │
│                     └──────────────────────────┘        │
└───────────────────────┬─────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     EventBus      /metrics       /api/v1/observability/*
     (WS推送)      (Prometheus)    (REST API)
```

### 数据流

```
组件动作 → metrics.record_xxx() → Prometheus Counter/Gauge
         → audit.log_event()    → structlog JSON → stdout
                                → SQLite lesson_store（反馈闭环）
         → alerts.evaluate()    → 阈值超标？
                                  ├─ warning → EventBus publish
                                  └─ critical → EventBus publish + audit log
         → collector.update()   → 组件健康状态（已有）

EventBus → WS 广播协程 → 前端驾驶舱（已有链路）
Prometheus /metrics → Prometheus Server scrape（已有端点，补指标）
```

## API 设计

### 新增端点

| 方法 | 路径 | 功能 | 请求/响应 |
|------|------|------|-----------|
| GET | `/api/v1/observability/metrics` | 业务指标快照 | `{ code:0, data: { tasks_total, llm_tokens_total, ... } }` |
| GET | `/api/v1/observability/alerts` | 当前活跃告警列表 | `{ code:0, data: [{ name, severity, message, since }] }` |
| GET | `/api/v1/observability/alerts/history` | 告警历史 | `{ code:0, data: [...], total: N }`，支持 `?limit=` |
| GET | `/api/v1/observability/audit?task_id=` | 任务审计日志 | `{ code:0, data: [{ timestamp, component, operation, ... }] }` |
| POST | `/api/v1/observability/lessons` | 记录教训 | `{ task_id, outcome, lesson }` → 201 |
| GET | `/api/v1/observability/lessons?domain=` | 查询教训库 | `{ code:0, data: [...] }` |

### 已有端点（不变）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/v1/observability/health` | 全组件健康 |
| GET | `/api/v1/observability/health/{component}` | 单组件健康 |
| GET | `/metrics` | Prometheus HTTP 指标（已有，instrumentator 提供） |

## 核心模块设计

### 1. `metrics.py` — Prometheus 业务指标

```python
# 任务指标
orbit_tasks_total = Counter("orbit_tasks_total", "任务总数", ["status"])
orbit_task_duration_seconds = Histogram("orbit_task_duration_seconds", "任务耗时", ["agent_role"])
orbit_active_tasks = Gauge("orbit_active_tasks", "当前活跃任务数")

# LLM 指标
orbit_llm_tokens_total = Counter("orbit_llm_tokens_total", "Token消耗", ["type", "model"])
orbit_llm_call_duration_seconds = Histogram("orbit_llm_call_duration_seconds", "LLM调用耗时")

# 防幻觉指标
orbit_hallucination_intercepted_total = Counter(
    "orbit_hallucination_intercepted_total", "防幻觉拦截次数", ["layer"]
)

# 熔断器指标
orbit_circuit_breaker_state = Gauge("orbit_circuit_breaker_state", "熔断器状态", ["breaker"])

# 沙箱指标
orbit_sandbox_pool_available = Gauge("orbit_sandbox_pool_available", "沙箱池可用数")
```

WHY 命名规范：`orbit_<component>_<metric>_<unit>`，遵循 Prometheus 最佳实践（`_total` 后缀用于 Counter，`_seconds` 用于时间）。

### 2. `audit.py` — 审计日志 + 反馈闭环

- **AuditLogger**: 封装 structlog，绑定额外 context（trace_id/task_id/component）。输出 JSON 到 stdout，无需 ELK 即可被 `docker logs` 或 `kubectl logs` 采集。
- **LessonStore**: SQLite 表 `agentops_lessons`，存任务成败教训。字段：`id/task_id/domain/outcome(SUCCESS|FAILURE)/lesson/tags/created_at`。

### 3. `alerts.py` — 告警规则引擎

纯内存规则引擎（参考 `compliance/rule_engine.py` 模式）：

```python
@dataclass
class AlertRule:
    name: str
    description: str
    severity: Literal["warning", "critical"]
    condition: Callable[[dict], bool]  # metrics_snapshot → bool
    cooldown_seconds: int = 300

class AlertEngine:
    def __init__(self, rules: list[AlertRule], event_bus: EventBus | None):
        ...
    def evaluate(self, metrics: dict) -> list[Alert]:
        """评估所有规则，触发时通过 EventBus 推送告警事件"""
```

内置 5 条规则（对应 PRD 代码块-4）：
- `high_token_consumption`: 单任务 Token > 50 → warning
- `high_z3_timeout_rate`: Z3 超时率 > 5% → critical
- `high_entropy`: 平均熵值 > 2.5 bits → warning
- `config_drift`: 配置漂移 > 0 → critical
- `sandbox_pool_exhausted`: 沙箱池 0 → critical

WHY 自研而非 AlertManager：MVP 单进程无需 Prometheus→AlertManager→webhook 完整链路。内存评估 + EventBus 推送延迟 <1ms。生产部署时 AlertManager rules.yml 提供等效规则。

### 4. `config.py` — AgentOps 配置

追加到 `core/config.py` 或独立文件（独立更干净）：

```python
@dataclass
class AgentOpsConfig:
    # 告警阈值
    TOKEN_THRESHOLD_WARNING: int = 50
    TOKEN_THRESHOLD_CRITICAL: int = 100
    Z3_TIMEOUT_RATE_THRESHOLD: float = 5.0
    ENTROPY_BITS_THRESHOLD: float = 2.5
    # 冷却时间
    ALERT_COOLDOWN_SECONDS: int = 300
    # 审计
    AUDIT_LOG_ENABLED: bool = True
    LESSON_STORE_ENABLED: bool = True
    # 自动修复（生产默认关闭）
    AUTO_FIX_ENABLED: bool = False
```

## 事件扩展

新增 `events/schemas.py`：

```python
class MetricsEvent(BaseModel):
    """metrics:snapshot 事件——定时推送到驾驶舱"""
    type: Literal["metrics:snapshot"] = "metrics:snapshot"
    task_id: str  # 或 "_system" 表示全局指标
    payload: dict[str, Any]  # { tasks_total: 42, active_tasks: 3, ... }
    timestamp: datetime

class AlertEvent(BaseModel):
    """alert:new / alert:resolved 事件"""
    type: Literal["alert:new", "alert:resolved"]
    task_id: str
    payload: dict[str, Any]  # { alert_name, severity, message, metrics_snapshot }
    timestamp: datetime
```

## 与 PRD 对照表

| PRD 验收标准 | 方案如何满足 | 实现位置 |
|-------------|-------------|---------|
| AC1: 8 组件埋点 100%，审计完整性 ≥95% | `metrics.py` 每个组件至少 1 Counter + 1 Histogram；`audit.py` structlog JSON 每操作一条记录 | `observability/metrics.py`, `audit.py` |
| AC2: 告警准确率 ≥90% | `alerts.py` 5 规则 + AlertManager rules.yml 互补；告警历史 API 支持人工评审 | `observability/alerts.py`, `configs/alertmanager/rules.yml` |
| AC3: 仪表盘 P99 <3s | Grafana Dashboard JSON 模板，数据源直连 Prometheus（无中间层） | `configs/grafana/dashboards/agentops-overview.json` |
| AC4: 完整调用链可查询 | structlog trace_id 关联 + `audit.py` 按 task_id 查询；P2 出 OTel 配置模板待基础设施就绪升级 | `observability/audit.py`, `configs/otel/` |
| AC5: WebSocket 实时推送 | metrics 快照 + 告警事件通过已有 EventBus→WS 链路推送，零新代码 | `events/schemas.py`, 复用已有 `ws/` |

## 测试策略

| 层 | 文件 | 用例数（预估） |
|----|------|---------------|
| 单元 | `tests/unit/test_observability.py` | 扩展现有 9→~25：新增 metrics 创建+递增、audit 记录+查询、alerts 规则评估+冷却、lesson CRUD |
| 集成 | `tests/integration/test_observability_api.py` | ~8：6 新端点 + 2 已有端点回归 |

### 关键测试场景

1. **metrics 递增正确**：`orbit_tasks_total.labels(status="success").inc()` → `_total` 值 +1
2. **audit 按 task_id 查询**：记录 3 条 → 按 task_id 过滤 → 返回 3 条
3. **告警触发+冷却**：Token 超标 → 触发告警 → 5分钟内再次超标 → 不重复触发
4. **告警严重度优先级**：同一组件同时 warning + critical → 汇总为 critical
5. **Lesson CRUD**：创建教训 → 按 domain 查询 → 返回匹配项

## 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| prometheus_client 是间接依赖，版本不锁定 | 构建断裂 | 确认 `prometheus-fastapi-instrumentator >=8.0` 依赖 `prometheus-client >=0.8.0`，API 稳定 |
| LessonStore SQLite 并发写 | 多 worker 写冲突 | WAL 模式 + 重试 3 次 |
| 告警规则硬编码 | 新增规则需改代码 | 预留 `alert_rules: list[AlertRule]` 注入点，后续可改为 YAML 文件加载 |
| 审计日志量增长 | 磁盘占满 | structlog 输出到 stdout，由容器日志轮转管理；LessonStore 按 `created_at` 索引，支持定期清理 |
