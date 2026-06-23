# PRD+ADR_F1：AgentOps 运维仪表盘

## Step F1：AgentOps 仪表盘——指标可视化 + 告警面板 + 熔断状态

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 后端 AgentOps 体系已交付完整可观测性能力（Prometheus 指标 + 审计日志 + 告警引擎 + 教训库，PR #25），但前端驾驶舱缺少对应的可视化面板。运维人员需要在不登录 Grafana 的情况下，直接在驾驶舱看到核心指标、活跃告警和熔断器状态。 |
| **用户故事** | 作为运维工程师，我希望在 Orbit 驾驶舱首页看到所有核心指标（任务成功率、Token 消耗、防幻觉拦截率、熔断器状态），并在告警触发时看到红色提醒卡片，以便在用户投诉前主动发现问题。 |
| **需求描述** | ① **指标卡片行**：顶部 4 个统计卡片——任务成功率(%)、当前活跃任务数、Token 消耗速率(tok/min)、防幻觉拦截总数。② **熔断器状态指示灯**：3 个圆点（ResourceGuard / Z3 / Sandbox），绿色=CLOSED，红色=OPEN，黄色=HALF_OPEN。③ **告警列表**（已有组件 AlertList 扩展）：显示最近告警（名称/严重度/时间），warning 黄色/critical 红色，点击查看详情。④ **指标趋势图**（已有 TokenChart 扩展）：新增防幻觉各层拦截率折线图(L1-L9)，合规检查结果柱状图(pass/warning/violation)。⑤ **健康状态面板**：8 核心组件健康指示（已有 /health API，增加 UI）。⑥ **数据刷新**：通过已有 WebSocket 推送 + 5s 轮询 `/api/v1/observability/metrics`。 |
| **范围 (Do/Don't)** | **Do：**指标卡片/熔断灯/告警列表/趋势图/健康面板；复用已有 WebSocket 通道；不新增 npm 依赖。<br>**Don't：**不替代 Grafana（那是生产级仪表盘）；不实现自定义指标查询（Phase 2）；不实现告警规则编辑（那是后端配置）。 |
| **数据契约** | **指标快照** `GET /api/v1/observability/metrics` → `{ tasks_total, active_tasks, llm_tokens_total, hallucination_intercepted_total, circuit_breaker_state, ... }`<br>**告警列表** `GET /api/v1/observability/alerts` → `[{ name, severity, message, since }]`<br>**健康状态** `GET /api/v1/observability/health` → `{ overall, components: [{ name, status, message }] }` |
| **异常定义** | ① API 不可达 → 指标卡片显示 "---" 灰色，不报错。② WebSocket 断开 → 自动降级为 HTTP 轮询（5s 间隔）。③ 告警列表为空 → 显示绿色 "✅ 无活跃告警"。 |
| **成功标准→验收** | **SC1:** 指标面板加载 → **AC1:** 页面打开 3s 内显示 4 个指标卡片的实际数值（非占位）。<br>**SC2:** 告警实时推送 → **AC2:** 后端触发告警后 5s 内前端显示对应告警卡片。<br>**SC3:** 熔断器状态准确 → **AC3:** 熔断器状态指示灯与实际 `/metrics` 数据一致（抽样 10 次全部匹配）。 |
| **待定决策** | **Q:** 指标刷新频率？ → **决议：** WebSocket 推送（0 延迟）+ HTTP 轮询 5s 兜底。<br>**Q:** 趋势图时间范围？ → **决议：** 默认最近 15 分钟，与 Grafana dashboard 一致。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Vue 3.4 + Pinia + ECharts 5 (已有)；复用 `useWebSocket` composable；不新增 npm 依赖。 |
| **决策** | 新增 `agentops` Pinia Store 管理指标/告警/健康数据；组件从 Store 读取，Store 通过 WebSocket + HTTP 双通道更新。 |
| **理由** | ① 指标数据跨组件共享（卡片/图表/指示灯），Store 是自然集中点。② 双通道保证实时性（WS）+ 可靠性（HTTP 兜底）。③ 不新增依赖，复用已有技术栈。 |
| **架构位置** | `frontend/src/stores/agentops.ts`（新增）、`frontend/src/components/metrics/MetricsCard.vue`（新增）、`frontend/src/components/metrics/CircuitBreakerLight.vue`（新增）、`frontend/src/components/metrics/HealthPanel.vue`（新增）、`frontend/src/components/alerts/AlertList.vue`（扩展）、`frontend/src/components/charts/TokenChart.vue`（扩展）、`frontend/src/views/DashboardView.vue`（扩展）。 |
| **实施细节** | **AgentOps Store：**`useAgentOpsStore` 持有 `metrics/ref`、`alerts/ref`、`health/ref`。`start()` 时建立 WS 监听 `metrics:snapshot` + `agentops:alert` 事件，同时启动 5s HTTP 轮询兜底。**MetricsCard：**Props 接收 `{ title, value, unit, trend }`，展示统计数值。**CircuitBreakerLight：**Props 接收 `{ name, state(0/1/2) }`，映射为绿/红/黄圆点。**HealthPanel：**遍历 health.components，每行显示组件名+状态图标+消息。 |
| **风险与缓解** | 风险：ECharts 在数据频繁更新时性能下降。缓解：使用 `notMerge: true` + `setOption` 局部更新，避免全量重绘。 |
| **需求错位** | 若未来需要自建指标查询语言（如 PromQL），当前 ECharts 渲染层可独立替换。 |
| **技术约束** | 不新增 npm 依赖；Vue 组件保持 <200 行；Pinia Store 不持有 ECharts 实例（组件自行管理）。 |
| **环境配置** | 无新增环境变量。 |
| **依赖链** | 依赖后端 PR #25（AgentOps 完整体系）提供 `/observability/*` API + WebSocket 事件。 |

---

## 组件树

```
DashboardView (扩展)
├── MetricsRow (新增)
│   ├── MetricsCard ×4 (新增)  # 成功率/活跃任务/Token速率/拦截数
│   └── CircuitBreakerLight ×3 (新增)  # RG/Z3/Sandbox
├── TokenChart (扩展——新增 L1-L9 折线)
├── ComplianceBarChart (新增)  # pass/warning/violation
├── AlertList (扩展——丰富信息)
└── HealthPanel (新增)  # 8 组件状态
```

## 测试策略

| 层 | 工具 | 用例 | 覆盖 |
|----|------|------|------|
| Store | vitest + pinia | 4 | agentops store 初始化/WS 消息更新/HTTP 轮询/告警去重 |
| 组件 | vitest + @vue/test-utils | 5 | MetricsCard 渲染/空值占位/CircuitBreakerLight 颜色映射/HealthPanel 组件列表/AlertList 空态 |
| E2E | Playwright | 3 | 仪表盘首屏加载 ≤3s / 告警卡片颜色正确 / 熔断灯状态同步 |
| **合计** | | **12** | |
