# 阶段3 实现记录 —— 完整 AgentOps 体系

## 方案引用

基于 [阶段2 技术方案](./阶段2-技术方案-AgentOps.md)（P0+P1 范围：代码层 4 模块 + 配置模板 4 文件）。

**严格按方案实现，无偏离。**

## 改动清单

### 新增文件（8 个）

| 文件 | 行数 | 目的 |
|------|------|------|
| `src/orbit/observability/config.py` | 55 | AgentOps 配置（阈值/开关），环境变量 `AGENTOPS_*` 注入 |
| `src/orbit/observability/metrics.py` | 157 | 12 类 Prometheus 业务指标 + snapshot() 快照函数 |
| `src/orbit/observability/audit.py` | 170 | AuditLogger（structlog 封装）+ LessonStore（SQLite 教训库） |
| `src/orbit/observability/alerts.py` | 213 | AlertEngine 内存规则引擎，5 内置规则 + 冷却 + 历史 |
| `configs/alertmanager/rules.yml` | 80 | P1 告警规则模板（5 条规则，对应内存引擎） |
| `configs/grafana/dashboard.json` | 130 | P1 Grafana 仪表盘模板（8 面板） |
| `configs/otel/otel-collector-config.yml` | 40 | P2 OTel Collector 配置模板 |
| `configs/logstash/pipeline.conf` | 55 | P2 Logstash 审计管道模板 |

### 修改文件（6 个）

| 文件 | 改动 |
|------|------|
| `src/orbit/observability/__init__.py` | +15 行：导出 4 个新模块 + 8 个类/函数 |
| `src/orbit/api/routes/observability.py` | +168 行：6 个新端点（metrics/alerts/audit/lessons） |
| `src/orbit/events/schemas.py` | +25 行：MetricsPayload + AgentOpsAlertPayload |
| `src/orbit/events/__init__.py` | +2 行：导出新事件类型 |
| `src/orbit/core/config.py` | +5 行：AGENTOPS_ENABLED 开关 |
| `tests/unit/test_observability.py` | +347 行：9→32 用例（+23 新测试） |

## 技术决策记录

### 为什么不用 OpenTelemetry SDK
structlog + trace_id 手动关联 + Prometheus metrics 已覆盖同等可观测性。OTel Collector + Tempo 基础设施未就绪时，SDK 只往 stdout 打 span，价值≈零。后续一行 `pip install opentelemetry-instrumentation-fastapi` 即可升级。

### 为什么自研 AlertEngine 而非直接用 AlertManager
MVP 单进程，Prometheus→AlertManager→webhook 链路延迟 >100ms。内存评估 + EventBus 推送 <1ms。生产部署通过 rules.yml 互补。

### 为什么 LessonStore 用 SQLite 而非 PostgreSQL
教训数据量小（每日 <100 条），SQLite 零配置。需要 PG 时迁移成本低（1 张表无外键）。

## 回溯对照

| PRD 验收标准 | 方案设计决策 | 代码位置 |
|-------------|-------------|---------|
| AC1: 埋点 100% + 审计完整性≥95% | metrics.py 12 类指标 + audit.py AuditLogger/LessonStore | `observability/metrics.py:21-103` / `observability/audit.py:44-160` |
| AC2: 告警准确率≥90% | AlertEngine 5 规则 + AlertManager 互补 | `observability/alerts.py:76-135` / `configs/alertmanager/rules.yml` |
| AC3: 仪表盘 P99<3s | Grafana JSON 模板 | `configs/grafana/dashboard.json` |
| AC4: 调用链可查询 | structlog trace_id + audit API + P2 OTel 模板 | `observability/audit.py:42` / `api/routes/observability.py:122-145` / `configs/otel/` |
| AC5: WS 实时推送 | EventBus 扩展 MetricsPayload + AlertPayload | `events/schemas.py:71-91` |

## 测试覆盖

| 测试类 | 用例数 | 覆盖范围 |
|--------|--------|---------|
| TestHealthCollector | 9 | 已有，回归通过 |
| TestMetrics | 8 | Counter/Gauge/Histogram 递增 + snapshot 完整性 |
| TestAuditLogger | 2 | 日志发射 + 禁用模式 |
| TestLessonStore | 4 | CRUD + 跨域查询 + 标签解析 |
| TestAlertEngine | 7 | 注册/评估/冷却/活跃/历史/内置规则/异常处理 |
| TestAgentOpsConfig | 2 | 默认值 + 环境变量覆盖 |
| **合计** | **32** | |

## 验证结果

- ruff: 零警告 ✅
- mypy --strict: 零错误 ✅
- pytest: 全量通过 ✅
- 零新依赖 ✅
- 零 API 破坏性变更（已有端点行为不变）✅
