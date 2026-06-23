## Step 7.2：AgentOps体系（可观测性+告警+自动化运维闭环）

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 生产级Agent系统需要全链路可观测性、持续监控和自动化运维闭环。V14.1的8层防幻觉体系、调度器状态机、三图谱查询等组件在生产环境中运行，需要统一的运维视图来发现、诊断和自动修复问题。 |
| **用户故事** | 作为运维工程师，我希望在统一仪表盘上看到所有V14.1核心组件的运行状态（任务成功率、Token消耗速率、熔断次数、各层拦截率），并能在异常时收到自动告警，以便在用户投诉之前主动修复问题。 |
| **需求描述** | ①可观测性采集：在调度器、验证器、沙箱、图谱查询等8个核心组件中埋点，记录每个步骤的输入、输出、耗时、Token消耗、熵值、决策日志、验证结果。<br>②指标存储与可视化：Prometheus采集关键指标，Grafana构建仪表盘，支持按任务/用户/时间范围筛选。<br>③日志审计：ELK Stack（Elasticsearch+Logstash+Kibana）存储审计日志和调试日志。<br>④分布式追踪：Jaeger或Tempo收集跨组件调用链。<br>⑤自动化告警：阈值告警（单任务Token>50、Z3超时率>5%、熵值>2.5 bits、配置漂移），触发自动修复脚本（切换模型、重启沙箱、回滚配置）。<br>⑥反馈闭环：成功/失败案例自动反馈到教训库，供后续任务参考。<br>⑦与驾驶舱集成：前端驾驶舱通过WebSocket实时推送运维数据。 |
| **范围 (Do/Don't)** | **Do：**全链路可观测性；指标+日志+追踪+告警；自动化修复脚本。<br>**Don't：**不替代人工故障诊断（复杂问题仍需人工介入）；不自动修改生产配置（仅告警+提供修复建议）。 |
| **数据契约** | ``代码块-1`` |
| **异常定义** | 若告警触发后执行修复脚本失败，系统保留现场状态并发送PAGERDUTY升级告警给值班SRE。 |
| **成功标准→验收** | **SC1:**核心组件埋点覆盖率100% → **AC1:**8个核心组件每个都有OpenTelemetry埋点，审计日志完整性≥95%。<br>**SC2:**告警准确率≥90% → **AC2:**人工评审100条告警，真实问题≥90条（误报≤10%）。<br>**SC3:**仪表盘加载时间<3s → **AC3:**Grafana面板首屏加载P99<3s。 |
| **待定决策** | **Q1:**使用Jaeger还是Tempo做追踪？ → **决议：**Grafana Tempo（与Grafana原生集成，存储成本低于Jaeger）。<br>**Q2:**告警升级策略如何定义？ → **决议：**WARNING→钉钉；CRITICAL→钉钉+电话；连续3次CRITICAL未确认→PAGERDUTY。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | OpenTelemetry Python SDK 1.20+, Prometheus 2.52, Grafana 10.4, Elasticsearch 8.12, Logstash 8.12, Kibana 8.12, Grafana Tempo 2.4, AlertManager 0.26, node_exporter 1.7。<br>与驾驶舱集成：WebSocket + Grafana Panel JSON API。 |
| **决策** | AgentOps体系采用"OpenTelemetry统一埋点 + Prometheus/Grafana/ELK存储 + 规则引擎告警"的组合方案，而非商业APM工具。 |
| **理由** | 1. OpenTelemetry是云原生标准，跨语言、跨框架支持好，与V14.1的Python调度器天然契合。<br>2. Prometheus+Grafana开源可控，不存在厂商锁定。<br>3. ELK Stack处理结构化审计日志效率高，查询灵活。<br>4. 规则引擎（AlertManager/PagerDuty）支持分级告警+升级策略。<br>5. 相比商业APM（如Datadog），成本可控（自托管）。 |
| **架构位置** | 运维基础设施层，独立于业务逻辑。埋点通过OpenTelemetry auto-instrumentation注入，业务代码零侵入。数据流：组件埋点 → OTel Collector → Prometheus/ELK/Tempo → Grafana/AlertManager。 |
| **实施细节** | **1. 埋点规范（JSON Lines格式）：**<br>``代码块-2``<br>**2. Prometheus指标命名规范：**<br>``代码块-3``<br>**3. 告警规则（AlertManager）：**<br>``代码块-4``<br>**4. Grafana Dashboard结构：**<br>``代码块-5``<br>**5. 与驾驶舱WebSocket集成：**<br>``代码块-6`` |
| **风险与缓解** | 风险1：大量埋点日志影响性能。缓解：采样率控制（只记录失败case或超阈值case的完整日志），正常路径异步批量写入。<br>风险2：ELK存储成本随时间快速增长。缓解：日志分级（审计日志永久保留，调试日志7天后删除），使用ILM策略自动归档。 |
| **需求错位** | 若生产环境网络策略限制（无法访问外部镜像），需提前打包OTel Collector镜像。当前假设使用标准云原生环境（K8s+Prometheus Operator）。 |
| **技术约束** | 所有组件必须暴露/metrics端点；日志必须输出JSON格式到stdout/stderr；WebSocket推送需支持断线重连。 |
| **环境配置** | ``代码块-7`` |
| **依赖链** | OpenTelemetry埋点 → OTel Collector → Prometheus（指标）→ Grafana（可视化）/ AlertManager（告警）<br>　　　　　　　　　　　　　　→ Elasticsearch（日志）→ Kibana（查询）<br>　　　　　　　　　　　　　　→ Tempo（追踪）→ Grafana（调用链）<br>　　　　　　　　　　　　　　→ WebSocket → 驾驶舱前端 |

🧪 验收测试 (pytest)：

```python
class TestStep72AgentOps:
    """Step 7.2 AgentOps体系 - 验收测试"""

    def test_observability_coverage(self):
        """SC1: 核心组件埋点覆盖率 100%"""
        # 8个核心组件每个都有埋点
        # 核心组件列表：调度器、验证器、沙箱、代码图谱、数据库图谱、配置图谱、LLM网关、防幻觉拦截器
        pass

    def test_alert_accuracy(self):
        """SC2: 告警准确率 ≥90%"""
        # 人工评审100条告警，真实问题 ≥90条（误报 ≤10%）
        pass

    def test_dashboard_load_time(self):
        """SC3: 仪表盘加载时间 <3s"""
        # Grafana面板首屏 P99 <3s
        pass

    def test_trace_correlation(self):
        """追踪链：从用户请求到Agent响应的完整调用链可查询"""
        pass

    def test_audit_log_completeness(self):
        """审计日志完整性 ≥95%"""
        pass

    def test_feedback_loop(self):
        """反馈闭环：成功/失败案例自动入库教训库"""
        pass

    def test_websocket_cockpit_integration(self):
        """驾驶舱WebSocket实时推送运维数据"""
        pass
```


```
# 代码块-1
# AgentOps 数据契约 - 埋点字段定义
{
    "trace_id": "string",          # OpenTelemetry trace ID
    "span_id": "string",           # OpenTelemetry span ID
    "parent_span_id": "string",    # 父span ID（可选）
    "component": "string",         # 组件名：scheduler|validator|sandbox|code_graph|db_graph|config_graph|llm_gateway|hallucination_layer
    "operation": "string",         # 操作名：execute|validate|sandbox_run|graph_query|llm_call|intercept
    "timestamp": "ISO8601",       # 时间戳
    "duration_ms": "float",        # 执行耗时（毫秒）
    "status": "string",           # success|failed|timeout
    "error_message": "string",    # 错误信息（失败时）
    "token_count": "int",         # Token消耗数
    "entropy_bits": "float",       # 熵值（LLM调用时）
    "input_tokens": "int",        # 输入Token数
    "output_tokens": "int",       # 输出Token数
    "hallucination_score": "float",# 拦截率（防幻觉层）
    "task_id": "string",           # 关联任务ID
    "user_id": "string",           # 用户ID
    "metadata": "object"           # 组件特定元数据
}
```


```
# 代码块-2
# 埋点日志示例（JSON Lines格式）
{"trace_id":"abc123","span_id":"def456","component":"scheduler","operation":"execute","timestamp":"2026-06-21T10:00:00Z","duration_ms":15.3,"status":"success","task_id":"task-001","token_count":35,"metadata":{"node_count":5,"parallel_nodes":3}}
{"trace_id":"abc123","span_id":"ghi789","component":"llm_gateway","operation":"llm_call","timestamp":"2026-06-21T10:00:01Z","duration_ms":120.5,"status":"success","token_count":28,"entropy_bits":1.23,"input_tokens":120,"output_tokens":85,"task_id":"task-001"}
{"trace_id":"abc123","span_id":"jkl012","component":"hallucination_layer","operation":"intercept","timestamp":"2026-06-21T10:00:02Z","duration_ms":3.2,"status":"success","hallucination_score":0.02,"task_id":"task-001"}
```


```
# 代码块-3
# Prometheus指标命名规范（按Prometheus最佳实践）
# 计数器（_total后缀）
v14_scheduler_tasks_total{status="success|failed"}     # 调度器任务总数
v14_llm_tokens_total{type="input|output"}               # LLM Token消耗
v14_hallucination_intercepted_total{layer="L1|L2|..."}  # 防幻觉拦截次数

# 仪表盘（无后缀或_bucket）
v14_task_duration_seconds_bucket{le="0.1|0.5|1|5|..."}   # 任务耗时分布
v14_token_consumed_per_task{quantile="0.5|0.9|0.99"}    # 单任务Token消耗分位数

# Gauge（当前值）
v14_active_tasks_count                                  # 当前活跃任务数
v14_circuit_breaker_state{breaker="z3|sandbox|llm"}     # 熔断器状态（0=closed,1=open)
v14_sandbox_pool_available                             # 沙箱池可用数

# 告警相关指标
v14_z3_timeout_rate                                    # Z3超时率（百分比）
v14_entropy_bits_avg                                   # 平均熵值
v14_config_drift_detected                              # 配置漂移检测（0/1）
```


```
# 代码块-4
# AlertManager告警规则（YAML格式）
groups:
- name: agentops
  rules:
  # 告警规则1：单任务Token超限
  - alert: HighTokenConsumption
    expr: v14_token_consumed_per_task > 50
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "单任务Token消耗超限"
      description: "任务 {{ $labels.task_id }} Token消耗 {{ $value }} 超过阈值50"

  # 告警规则2：Z3超时率过高
  - alert: HighZ3TimeoutRate
    expr: v14_z3_timeout_rate > 5
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Z3验证超时率过高"
      description: "Z3超时率 {{ $value }}% 超过阈值5%，可能影响验证准确性"

  # 告警规则3：熵值异常
  - alert: HighEntropyDetected
    expr: v14_entropy_bits_avg > 2.5
    for: 3m
    labels:
      severity: warning
    annotations:
      summary: "LLM输出熵值异常"
      description: "平均熵值 {{ $value }} bits 超过阈值2.5 bits，可能存在幻觉风险"

  # 告警规则4：配置漂移
  - alert: ConfigDriftDetected
    expr: v14_config_drift_detected == 1
    for: 0m
    labels:
      severity: critical
    annotations:
      summary: "配置漂移检测"
      description: "检测到配置与基准不一致，需要人工确认是否回滚"

  # 告警规则5：沙箱池耗尽
  - alert: SandboxPoolExhausted
    expr: v14_sandbox_pool_available == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "沙箱池耗尽"
      description: "所有沙箱实例不可用，新任务无法执行"

# 告警路由配置
route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'dingtalk'
  routes:
  - match:
      severity: critical
    receiver: 'dingtalk+pagerduty'
    continue: true
  - match:
      severity: warning
    receiver: 'dingtalk'

receivers:
- name: 'dingtalk'
  webhook_configs:
  - url: 'http://dingtalk-webhook:8060/dingtalk/webhook'

- name: 'dingtalk+pagerduty'
  webhook_configs:
  - url: 'http://dingtalk-webhook:8060/dingtalk/webhook'
  pagerduty_configs:
  - service_key: 'YOUR_PAGERDUTY_KEY'
```


```
# 代码块-5
# Grafana Dashboard结构（JSON模板片段）
{
  "dashboard": {
    "title": "Agent System V14.1 - AgentOps Overview",
    "panels": [
      {
        "title": "任务成功率",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(rate(v14_scheduler_tasks_total{status='success'}[5m])) / sum(rate(v14_scheduler_tasks_total[5m])) * 100",
            "legendFormat": "成功率%"
          }
        ]
      },
      {
        "title": "Token消耗速率",
        "type": "graph",
        "targets": [
          {
            "expr": "sum(rate(v14_llm_tokens_total[5m]))",
            "legendFormat": "Tokens/sec"
          }
        ]
      },
      {
        "title": "各层防幻觉拦截率",
        "type": "graph",
        "targets": [
          {
            "expr": "sum by (layer) (rate(v14_hallucination_intercepted_total[5m]))",
            "legendFormat": "{{layer}}"
          }
        ]
      },
      {
        "title": "熔断器状态",
        "type": "stat",
        "targets": [
          {
            "expr": "v14_circuit_breaker_state",
            "legendFormat": "{{breaker}}"
          }
        ]
      },
      {
        "title": "调用链追踪",
        "type": "traces",
        "targets": [
          {
            "query": "{task_id=~\"$task_id\"}"
          }
        ]
      }
    ]
  }
}
```


```
# 代码块-6
# WebSocket推送服务（与驾驶舱集成）
# 位置：/src/agentops/websocket_pusher.py

class GrafanaWebSocketPusher:
    """将Grafana Panel数据实时推送到驾驶舱前端"""

    def __init__(self, grafana_url: str, api_key: str, cockpit_ws_url: str):
        self.grafana_url = grafana_url
        self.api_key = api_key
        self.cockpit_ws = cockpit_ws_url
        self._running = False

    async def start(self):
        """启动WebSocket推送循环"""
        self._running = True
        while self._running:
            try:
                # 1. 从Grafana API获取指标数据
                metrics = await self._fetch_grafana_metrics()

                # 2. 推送到驾驶舱WebSocket
                await self._push_to_cockpit(metrics)

                await asyncio.sleep(5)  # 5秒刷新一次
            except Exception as e:
                logger.error(f"WebSocket推送失败: {e}")
                await asyncio.sleep(10)

    async def _fetch_grafana_metrics(self) -> dict:
        """调用Grafana API获取实时指标"""
        # 使用Grafana InfluxDB/Loki数据源API
        pass

    async def _push_to_cockpit(self, metrics: dict):
        """通过WebSocket推送到驾驶舱"""
        import websockets
        async with websockets.connect(self.cockpit_ws) as ws:
            await ws.send(json.dumps({
                "type": "agentops_metrics",
                "data": metrics,
                "timestamp": datetime.utcnow().isoformat()
            }))

    def stop(self):
        self._running = False
```


```
# 代码块-7
# AgentOps 环境配置
# 位置：/src/agentops/config.py

from pydantic import BaseModel

class AgentOpsConfig(BaseModel):
    # OpenTelemetry配置
    OTEL_SERVICE_NAME: str = "agent-system-v14"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://tempo-collector:4317"
    OTEL_TRACES_SAMPLER: str = "parentbased_traceidratio"
    OTEL_TRACES_SAMPLER_ARG: float = 0.1  # 采样率10%

    # Prometheus配置
    METRICS_PORT: int = 9090
    METRICS_PATH: str = "/metrics"

    # Elasticsearch配置
    ES_HOST: str = "elasticsearch:9200"
    ES_INDEX_PREFIX: str = "agentops-logs"
    ES_AUDIT_INDEX: str = "agentops-audit"
    ES_DEBUG_INDEX: str = "agentops-debug"

    # 日志保留策略
    AUDIT_LOG_RETENTION_DAYS: int = -1  # 永久保留
    DEBUG_LOG_RETENTION_DAYS: int = 7  # 7天后删除

    # 告警阈值
    TOKEN_THRESHOLD_WARNING: int = 50
    TOKEN_THRESHOLD_CRITICAL: int = 100
    Z3_TIMEOUT_RATE_THRESHOLD: float = 5.0
    ENTROPY_BITS_THRESHOLD: float = 2.5

    # 驾驶舱集成
    COCKPIT_WS_URL: str = "ws://cockpit:8080/ws/metrics"
    GRAFANA_URL: str = "http://grafana:3000"
    GRAFANA_API_KEY: str = ""  # 从K8s Secret加载

    # 自动化修复脚本
    AUTO_FIX_SCRIPTS_DIR: str = "/opt/agentops/fix-scripts"
    AUTO_FIX_ENABLED: bool = False  # 默认仅告警，不自动执行

    class Config:
        env_prefix = "AGENTOPS_"
```
