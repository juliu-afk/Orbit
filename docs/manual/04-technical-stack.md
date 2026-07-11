# 04 · 技术方案 · Technical Design

[← 返回目录 Back to index](README.md) · [← 上一章 九层防幻觉](03-hallucination-defense.md)

> 本章覆盖技术选型的"怎么实现"：技术栈、LLM 网关与三层路由、沙箱、存储、可观测性。开发者主读。

---

## 4.1 技术栈矩阵 · Stack Matrix

| 层级 | 组件 | 版本 | 选型理由 |
|---|---|---|---|
| 主语言 | Python | 3.11–3.13 | 异步生态成熟，AI/ML 库齐全 |
| 包管理 | Poetry | 1.8.2 | 锁版本、可复现构建 |
| LLM 网关 | LiteLLM | ≥1.40 | 统一多 provider 接口 + 追踪 + 降级 |
| API | FastAPI + Pydantic v2 + Uvicorn | ≥0.110 | 异步 + 类型契约 + 自动 OpenAPI |
| ORM | SQLAlchemy 2.0.25 + Alembic 1.13 | — | `Mapped`/`mapped_column` 现代风格 |
| 代码图谱 | CodeGraph（Tree-sitter） | latest | 多语言确定性解析 |
| 审计存储 | PostgreSQL 15 + Redis 7.2 | ≥15 / ≥7 | 冷热双层，审计 + 缓存 |
| 沙箱 | Docker Engine | ≥24 | 强隔离执行 LLM 代码 |
| 前端 | Vue3 + Pinia + Tailwind v4 | ≥3.4 | 组合式 API + 集中状态 |
| 桌面壳 | Tauri (Rust WebView2) | latest | 20MB 级 exe，无 Electron 臃肿 |
| 测试 | pytest / pytest-asyncio / mutmut / Playwright | ≥8.0 | 单元→变异→E2E 全覆盖 |

## 4.2 LLM 网关与三层模型路由 · Gateway & 3-Tier Routing

**中文**：所有 LLM 调用**必须**经 LiteLLM 网关（`gateway/`），禁止直连 provider——这是不可妥协项（统一追踪 + 降级）。网关之上是**智能路由**（`router/`）：RouterAgent 评估任务复杂度，推荐模型级别（T1/T2/T3），可被 `CC_SWITCH` 强制覆盖。

**English**: Every LLM call **must** go through the LiteLLM gateway (`gateway/`) — direct provider calls are forbidden (unified tracing + fallback). Above it sits smart routing (`router/`): RouterAgent scores task complexity and recommends a model tier (T1/T2/T3), overridable via `CC_SWITCH`.

配置的模型（[`docker-compose.yml`](../../docker-compose.yml)）：DeepSeek V4 Pro/Flash + GLM-5.2/4.7 Flash。三层路由的意图：简单任务走便宜快模型（Flash），复杂任务走强模型（Pro），成本与质量动态平衡。

> 相关：`sharding/` 动态任务分片、`compression/` 上下文压缩（CascadePruner 4 级级联裁剪）共同把单任务 Token 压到设计目标 ≤35。

## 4.3 沙箱执行 · Sandbox

- 主方案 **DockerSandbox**：Docker 隔离容器执行 LLM 生成代码，`SANDBOX_TIMEOUT_SECONDS`（默认 30s）硬超时。
- 兜底 **ProcessSandbox**：无 Docker 环境时降级为进程隔离。
- 自动选择：运行时探测 Docker 可用性。
- 红线：**LLM 生成代码禁止在宿主机直接执行**（安全基线）。
- 用途：既是独立能力（`/api` 沙箱端点），也是防幻觉 L7 层的执行引擎。

## 4.4 存储架构 · Storage

| 存储 | 用途 | 冷热 |
|---|---|---|
| **CodeGraph SQLite** | 五图谱统一存储（代码/数据库/配置/知识） | 本地、零 Token、<50ms |
| `data/meta_graph.db` | 元图谱独立库（12 种跨图谱关系） | 本地 |
| **Redis 7.2** | 检查点热存储（TTL=1h）、熔断器状态、审计缓存 | 热 |
| **PostgreSQL 15** | 检查点冷备份、审计链 `task_audit_trail`、成本记录 | 冷 |
| SQLite（开发） | `DATABASE_URL=sqlite+aiosqlite:///./data/graph.db` | 零依赖启动 |
| PostgreSQL（生产） | `DATABASE_URL=postgresql+asyncpg://...` | 生产 |

**零依赖启动**是刻意设计：开发态用 SQLite，双击 exe 即可跑，无需 Docker/Redis/PostgreSQL。生产态切 PostgreSQL + Redis。

## 4.5 可观测性 · Observability

`observability/` 模块提供 AgentOps 全栈可观测：

- **指标**：Prometheus `/metrics`（4 核心业务指标：调度延迟、幻觉验证、熔断、成本）。
- **审计**：`task_audit_trail` + 反馈引擎（feedback）+ 教训库（lessons）。
- **Trace**：全链路追踪，7 核心模块 40+ span，`trace_spans` 表（`003_trace_spans.sql`）。
- **告警**：告警引擎 + AlertManager 规则（`configs/alertmanager/rules.yml`）。
- **看板**：Grafana dashboard（`configs/grafana/dashboard.json`）。
- **采集**：OpenTelemetry collector（`configs/otel/`）+ Logstash pipeline。

## 4.6 部署形态 · Deployment Forms

| 形态 | 技术 | 场景 |
|---|---|---|
| 桌面 exe | Tauri + PyInstaller 内嵌后端 | 单机、双击即用（端口 18888） |
| 源码 | Poetry + Uvicorn `--reload` | 开发（端口 8000，`make dev`） |
| Docker 全栈 | docker-compose（PG/Redis/LiteLLM） | 生产（端口 18888，`make up`） |
| Kubernetes | Helm Chart（`chart/orbit/`）+ Argo Rollouts | 灰度/金丝雀 + SLO 自动回滚（`configs/k8s/`） |

灾难恢复见 [`docs/SOP-灾难恢复手册.md`](../SOP-灾难恢复手册.md)；DR 恢复 CLI 见 `scripts/dr/recover.py`（list/verify/recover）。

---

[← 返回目录](README.md) · [下一章：使用说明 →](05-usage-guide.md)
</content>
