# 07 · 技术方案 || Technical Design

[← 返回目录 || Back to index](README.md) · [← 上一章：九层防幻觉 || Prev: Hallucination Defense](06-hallucination-defense.md)

> 本章覆盖技术选型的"怎么实现"：技术栈、LLM 网关与三层路由、沙箱、存储、可观测性。开发者主读。 || This chapter covers the "how" of the technical design: stack matrix, LLM gateway with three-tier routing, sandbox, storage, and observability. Primarily for developers.

---

## 7.1 技术栈矩阵 || Stack Matrix

| 层级 || Layer | 组件 || Component | 版本 || Version | 选型理由 || Rationale |
|---|---|---|---|
| 主语言 || Runtime | Python | 3.11–3.13 | 异步生态成熟，AI/ML 库齐全 || Mature async ecosystem, rich AI/ML libraries |
| 包管理 || Package Manager | Poetry | 1.8.2 | 锁版本、可复现构建 || Locked versions, reproducible builds |
| LLM 网关 || LLM Gateway | LiteLLM | ≥1.40 | 统一多 provider 接口 + 追踪 + 降级 || Unified multi-provider interface + tracing + fallback |
| API | FastAPI + Pydantic v2 + Uvicorn | ≥0.110 | 异步 + 类型契约 + 自动 OpenAPI || Async + type contracts + auto OpenAPI |
| ORM | SQLAlchemy 2.0.25 + Alembic 1.13 | — | `Mapped`/`mapped_column` 现代风格 || Modern `Mapped`/`mapped_column` style |
| 代码图谱 || Code Graph | CodeGraph（Tree-sitter） | latest | 多语言确定性解析 || Deterministic multi-language parsing |
| 审计存储 || Audit Storage | PostgreSQL 15 + Redis 7.2 | ≥15 / ≥7 | 冷热双层，审计 + 缓存 || Hot/cold two-tier, audit + cache |
| 沙箱 || Sandbox | Docker Engine | ≥24 | 强隔离执行 LLM 代码 || Strong isolation for LLM-generated code |
| 前端 || Frontend | Vue3 + Pinia + Tailwind v4 | ≥3.4 | 组合式 API + 集中状态 || Composition API + centralized state |
| 桌面壳 || Desktop Shell | Tauri (Rust WebView2) | latest | 20MB 级 exe，无 Electron 臃肿 || 20MB exe, no Electron bloat |
| 测试 || Testing | pytest / pytest-asyncio / mutmut / Playwright | ≥8.0 | 单元→变异→E2E 全覆盖 || Unit → mutation → E2E full coverage |

## 7.2 LLM 网关与三层模型路由 || Gateway & 3-Tier Routing

所有 LLM 调用**必须**经 LiteLLM 网关（`gateway/`），禁止直连 provider——这是不可妥协项（统一追踪 + 降级）。网关之上是**智能路由**（`router/`）：RouterAgent 评估任务复杂度，推荐模型级别（T1/T2/T3），可被 `CC_SWITCH` 强制覆盖。 || Every LLM call **must** go through the LiteLLM gateway (`gateway/`) — direct provider calls are forbidden (unified tracing + fallback). Above it sits smart routing (`router/`): RouterAgent scores task complexity and recommends a model tier (T1/T2/T3), overridable via `CC_SWITCH`.

配置的模型（[`docker-compose.yml`](../../docker-compose.yml)）：DeepSeek V4 Pro/Flash + GLM-5.2/4.7 Flash。三层路由的意图：简单任务走便宜快模型（Flash），复杂任务走强模型（Pro），成本与质量动态平衡。 || Configured models ([`docker-compose.yml`](../../docker-compose.yml)): DeepSeek V4 Pro/Flash + GLM-5.2/4.7 Flash. The three-tier routing strategy: simple tasks use cheap fast models (Flash), complex tasks use powerful models (Pro), dynamically balancing cost and quality.

> 相关：`sharding/` 动态任务分片、`compression/` 上下文压缩（CascadePruner 4 级级联裁剪）共同把单任务 Token 压到设计目标 ≤35。 || Related: `sharding/` dynamic task sharding, `compression/` context compression (CascadePruner 4-level cascade pruning) together keep per-task tokens at or below the design target of 35.

## 7.3 沙箱执行 || Sandbox

- 主方案 **DockerSandbox**：Docker 隔离容器执行 LLM 生成代码，`SANDBOX_TIMEOUT_SECONDS`（默认 30s）硬超时。 || Primary: **DockerSandbox** — Docker isolated container for executing LLM-generated code, with `SANDBOX_TIMEOUT_SECONDS` (default 30s) hard timeout.
- 兜底 **ProcessSandbox**：无 Docker 环境时降级为进程隔离。 || Fallback: **ProcessSandbox** — degrades to process isolation when Docker is unavailable.
- 自动选择：运行时探测 Docker 可用性。 || Auto-selection: probes Docker availability at runtime.
- 红线：**LLM 生成代码禁止在宿主机直接执行**（安全基线）。 || Red line: **LLM-generated code must never execute directly on the host** (security baseline).
- 用途：既是独立能力（`/api` 沙箱端点），也是防幻觉 L7 层的执行引擎。 || Usage: serves both as a standalone capability (`/api` sandbox endpoint) and as the execution engine for Hallucination Defense L7.

## 7.4 存储架构 || Storage

| 存储 || Storage | 用途 || Purpose | 冷热 || Hot/Cold |
|---|---|---|
| **CodeGraph SQLite** | 五图谱统一存储（代码/数据库/配置/知识） || Unified five-graph storage (code/database/config/knowledge) | 本地、零 Token、<50ms || Local, zero-token, <50ms |
| `data/meta_graph.db` | 元图谱独立库（12 种跨图谱关系） || Separate meta-graph store (12 cross-graph relationship types) | 本地 || Local |
| **Redis 7.2** | 检查点热存储（TTL=1h）、熔断器状态、审计缓存 || Checkpoint hot storage (TTL=1h), circuit-breaker state, audit cache | 热 || Hot |
| **PostgreSQL 15** | 检查点冷备份、审计链 `task_audit_trail`、成本记录 || Checkpoint cold backup, audit chain `task_audit_trail`, cost records | 冷 || Cold |
| SQLite（开发） || SQLite (development) | `DATABASE_URL=sqlite+aiosqlite:///./data/graph.db` | 零依赖启动 || Zero-dependency startup |
| PostgreSQL（生产） || PostgreSQL (production) | `DATABASE_URL=postgresql+asyncpg://...` | 生产 || Production |

**零依赖启动**是刻意设计：开发态用 SQLite，双击 exe 即可跑，无需 Docker/Redis/PostgreSQL。生产态切 PostgreSQL + Redis。 || **Zero-dependency startup** is intentional: development uses SQLite — double-click the exe and it runs, no Docker/Redis/PostgreSQL needed. Production switches to PostgreSQL + Redis.

## 7.5 可观测性 || Observability

`observability/` 模块提供 AgentOps 全栈可观测： || The `observability/` module provides full-stack AgentOps observability:

- **指标**：Prometheus `/metrics`（4 核心业务指标：调度延迟、幻觉验证、熔断、成本）。 || **Metrics**: Prometheus `/metrics` (4 core business metrics: scheduling latency, hallucination verification, circuit breaker, cost).
- **审计**：`task_audit_trail` + 反馈引擎（feedback）+ 教训库（lessons）。 || **Audit**: `task_audit_trail` + feedback engine + lessons store.
- **Trace**：全链路追踪，7 核心模块 40+ span，`trace_spans` 表（`003_trace_spans.sql`）。 || **Trace**: End-to-end tracing across 7 core modules with 40+ spans, stored in the `trace_spans` table (`003_trace_spans.sql`).
- **告警**：告警引擎 + AlertManager 规则（`configs/alertmanager/rules.yml`）。 || **Alerting**: Alert engine + AlertManager rules (`configs/alertmanager/rules.yml`).
- **看板**：Grafana dashboard（`configs/grafana/dashboard.json`）。 || **Dashboard**: Grafana dashboard (`configs/grafana/dashboard.json`).
- **采集**：OpenTelemetry collector（`configs/otel/`）+ Logstash pipeline。 || **Collection**: OpenTelemetry collector (`configs/otel/`) + Logstash pipeline.

## 7.6 部署形态 || Deployment Forms

| 形态 || Form | 技术 || Technology | 场景 || Scenario |
|---|---|---|
| 桌面 exe || Desktop exe | Tauri + PyInstaller 内嵌后端 || Tauri + PyInstaller embedded backend | 单机、双击即用（端口 18888） || Standalone, double-click to run (port 18888) |
| 源码 || Source | Poetry + Uvicorn `--reload` | 开发（端口 8000，`make dev`） || Development (port 8000, `make dev`) |
| Docker 全栈 || Docker full-stack | docker-compose（PG/Redis/LiteLLM） | 生产（端口 18888，`make up`） || Production (port 18888, `make up`) |
| Kubernetes | Helm Chart（`chart/orbit/`）+ Argo Rollouts | 灰度/金丝雀 + SLO 自动回滚（`configs/k8s/`） || Canary/gray rollout + SLO auto-rollback (`configs/k8s/`) |

灾难恢复见 [`docs/SOP-灾难恢复手册.md`](../SOP-灾难恢复手册.md)；DR 恢复 CLI 见 `scripts/dr/recover.py`（list/verify/recover）。 || See [`docs/SOP-灾难恢复手册.md`](../SOP-灾难恢复手册.md) for disaster recovery; DR CLI at `scripts/dr/recover.py` (list/verify/recover).

---

[← 返回目录 || Back to index](README.md) · [下一章：使用说明 → || Next: Usage Guide →](08-usage-guide.md)
