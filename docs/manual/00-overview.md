# 00 · 总览 || Overview

[← 返回目录 || Back to index](README.md)

---

## 0.1 Orbit 是什么 || What Orbit Is

Orbit 是一套**多智能体软件开发自循环系统**，锚定在**编排层（orchestration layer）**。它不是单智能体执行工具（如 Claude Code、Codex），而是让一群 AI Agent 协作完成软件开发全流程的**治理系统**。核心价值只有四个词：**编排、治理、验证、追溯**。 || Orbit is a **multi-agent, self-looping software-development system** anchored at the **orchestration layer**. It is not a single-agent coding tool (Claude Code, Codex); it is a **governance system** that coordinates a fleet of AI agents through the entire development lifecycle. Its value reduces to four words: **orchestrate, govern, validate, trace**.

> 架构锚定声明（Step 0.4，见 [`docs/charter.md:87-90`](../charter.md)）：所有 Prompt / Context 设计必须服务于**协作流程的编排与治理**，而非单次代码生成质量。若 Prompt 退化为"你是一个 Python 专家"这类执行层风格，评审直接打回。 || Architecture-anchor statement (Step 0.4, see [`docs/charter.md:87-90`](../charter.md)): All Prompt / Context design must serve **collaboration-process orchestration and governance**, not single-shot code quality. If a Prompt degenerates into execution-layer style like "You are a Python expert," the review rejects it outright.

## 0.2 为什么需要它 || Why It Exists

单个编码 Agent 能写代码，但**无法自我治理**：无法保证不产生幻觉、无法回滚到安全状态、无法解释"这行代码为什么这么写"。Orbit 用五个能力把单 Agent 的"能写"升级为团队级的"可信交付"： || A single coding agent can write code but cannot **govern itself** — it cannot guarantee freedom from hallucination, cannot roll back to a safe state, cannot explain why a line was written. Orbit adds five capabilities that turn "can write" into "trustworthy delivery":

1. **多 Agent 协作** — 5 核心角色（架构师/开发/审查/QA/配置管理）分工。 || **Multi-Agent Collaboration** — 5 core roles (Architect/Developer/Reviewer/QA/ConfigManager).
2. **状态机调度** — 自研 asyncio 有限状态机，每个状态转换存检查点、可回滚。 || **State-Machine Scheduler** — self-built asyncio FSM, every state transition has a checkpoint, rollback-capable.
3. **五图谱记忆** — 代码/数据库/配置/知识/元图谱，让 Agent"知道全局"。 || **5-Graph Memory** — Code/DB/Config/Knowledge/Meta graphs, giving agents "global awareness".
4. **9 层防幻觉** — 从静态校验到 Docker 沙箱执行的纵深防御。 || **9-Layer Hallucination Defense** — defense-in-depth from static checks to Docker sandbox execution.
5. **审计链** — 每个 Agent 动作、每次 LLM 调用、每条验证结果全部可追溯。 || **Audit Trail** — every agent action, every LLM call, every validation result is traceable.

## 0.3 核心指标 || Key Metrics

> 目标值来自 [`docs/charter.md`](../charter.md)；"当前"随覆盖率冲刺演进，以路线图为准。 || Targets from [`docs/charter.md`](../charter.md); "current" values evolve with coverage sprints; see the roadmap for the latest.

| 指标 || Metric | 目标 || Target | 测量 || How measured |
|---|---|---|---|
| 调度层延迟 || Scheduling latency | ≤1500ms（预警 1200ms）|| ≤1500ms (warning at 1200ms) | Prometheus `orbit_scheduling_latency_seconds` |
| 幻觉率 || Hallucination rate | <3% | Prometheus `orbit_hallucination_validations_total` |
| 幻觉拦截率 || Interception rate | ≥98% | 9 层防幻觉复合 || 9-layer hallucination defense combined |
| 熔断决策延迟 || Breaker decision latency | ≤12ms | 纯内存判断 || Pure in-memory decision |
| 图谱查询延迟 || Graph query latency | <50ms | SQLite 索引 || SQLite index |
| CI 覆盖率门禁 || Coverage gate | ≥80% | `pytest --cov-fail-under=80` |
| 单任务 Token（设计目标）|| Token per task (design target) | ≤35 | LiteLLM usage 统计 || LiteLLM usage statistics |
| 源码模块 || Source modules | 48 | `src/orbit/` |
| 测试文件 || Test files | ~359 | `tests/` |

## 0.4 与单 Agent 工具的定位差异 || Positioning vs Single-Agent Tools

| 维度 || Dimension | 自研调度器 Orbit || Self-built Scheduler Orbit | 黑盒框架（如 CrewAI）|| Black-box framework (e.g., CrewAI) |
|---|---|---|---|
| 单任务 Token || Token per task | ≤35（目标）|| ≤35 (target) | ~4.5K（基准）|| ~4.5K (baseline) |
| 单次运行耗时 || Latency per run | ~1.5s（目标，不含验证）|| ~1.5s (target, without validation) | ~32s（含验证）|| ~32s (with validation) |
| 可控性 || Controllability | 完全可审计、可修改 || Fully auditable, modifiable | 黑盒调度，难审计 || Black-box scheduling, hard to audit |
| 内存占用 || Memory footprint | ~50MB | ~200MB 框架开销 || ~200MB framework overhead |

> 数据来源：[`docs/开发计划/00-架构总览.md:83-91`](../开发计划/00-架构总览.md)。选择自研而非现成框架的完整论证见 [01 设计哲学 §1.3](01-design-philosophy.md)。 || Source: [`docs/开发计划/00-架构总览.md:83-91`](../开发计划/00-架构总览.md). Full rationale for choosing self-built over off-the-shelf frameworks is in [01 Design Philosophy §1.3](01-design-philosophy.md).

## 0.5 技术栈全景 || Technology Stack

| 层级 || Layer | 组件 || Component | 版本 || Version |
|---|---|---|---|
| 主语言 || Language | Python | 3.11–3.13 |
| 包管理 || Packaging | Poetry | 1.8.2 |
| LLM 网关 || Gateway | LiteLLM | ≥1.40 |
| API | FastAPI + Pydantic v2 + Uvicorn | ≥0.110 |
| ORM | SQLAlchemy 2.0.25 + Alembic 1.13 | — |
| 代码图谱 || Code graph | CodeGraph（Tree-sitter） | latest |
| 审计存储 || Audit store | PostgreSQL + Redis | ≥15 / ≥7 |
| 沙箱 || Sandbox | Docker Engine | ≥24 |
| 前端 || Frontend | Vue3 + Pinia + Tailwind v4 | ≥3.4 |
| 桌面壳 || Desktop shell | Tauri (Rust WebView2) | latest |
| 测试 || Testing | pytest / pytest-asyncio / mutmut / Playwright | ≥8.0 |

完整技术方案见 [04 技术方案 || Technical Design](04-technical-stack.md)。 || For the full technical design, see [04 Technical Design](04-technical-stack.md).

## 0.6 全景速览图 || Bird's-Eye View

```
                     ┌─────────────────────────────────────────────┐
  用户/User ──REST──▶ │  FastAPI (api/)  ·  WebSocket 驾驶舱 (ws/)   │
                     └───────────────┬─────────────────────────────┘
                                     │ Layer 1: 系统→Agent (asyncio 协程)
                           ┌─────────▼──────────┐
                           │  Scheduler 状态机   │◀── Checkpoint 检查点（存/回滚）
                           │  (scheduler/)      │◀── ResourceGuard 熔断
                           └─────────┬──────────┘
              Layer 3: A2A (MessageBus)  │  Layer 2: Agent→工具 (MCP)
        ┌────────────┬────────────┬─────┴──────┬────────────┐
        ▼            ▼            ▼            ▼            ▼
   Architect     Developer     Reviewer       QA      ConfigManager   (agents/)
        └────────────┴─────┬──────┴────────────┴────────────┘
                           │ 生成代码
                    ┌──────▼────────────────────────────────┐
                    │  9 层防幻觉 (hallucination/ + compliance/) │
                    │  L1图谱→L4类型→L3熵→L2追踪→L6合约         │
                    │  →L8配置→L7沙箱→L5 Z3 →L9合规            │
                    └──────┬────────────────────────────────┘
                           │ 全程读取/写入
   ┌───────────────────────▼───────────────────────────────┐
   │ 五图谱 (graph/ + knowledge/)：代码·数据库·配置·知识·元图谱 │
   └───────────────────────┬───────────────────────────────┘
                           │ 全程记录
                    ┌──────▼──────────────────────┐
                    │ 审计链 task_audit_trail (observability/) │
                    └─────────────────────────────┘
```

---

[← 返回目录 || Back to index](README.md) · [下一章：设计哲学 → || Next: Design Philosophy →](01-design-philosophy.md)
