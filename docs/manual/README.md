# Orbit 说明书 || Orbit Manual

> 轻量级多 Agent 软件开发自循环系统 —— 完整说明书。 || A lightweight multi-agent, self-looping software development system — the complete manual.

本说明书面向三类读者，用一套带目录的文档覆盖 Orbit 的设计哲学、能力边界、整体架构、端到端流程、方法论与理论、技术方案、使用说明、再开发说明。 || This manual serves three audiences and covers Orbit's design philosophy, capability boundaries, architecture, end-to-end workflow, methodology & theory, technical design, usage, and re-development in one indexed document set.

| 读者 || Reader | 你想知道 || What you want | 建议路径 || Suggested path |
|---|---|---|
| 使用者 || User | 怎么装、怎么跑、能做什么 || How to install, run, and what it can do | 00 → 02 → 08 → 09 |
| 开发者 || Developer | 怎么改、流程怎么走、怎么构建 || How to modify, how the flow works, how to build | 00 → 03 → 04 → 10 |
| 研究者 || Researcher | 为什么这么设计、用了什么理论 || Why it is designed this way, what theory it uses | 01 → 03 → 05 → 06 → 11 |

---

## 目录 || Table of Contents

### 第一部分 · 认识 Orbit || Part I · Understanding Orbit

| # | 文档 || Document | 内容 || Content |
|---|---|---|
| 00 | [总览 || Overview](00-overview.md) | 项目定位、核心指标、技术栈全景、读者导航 || Positioning, key metrics, tech-stack overview, navigation |
| 01 | [设计哲学 || Design Philosophy](01-design-philosophy.md) | 为何存在、为何锚定编排层、为何自研调度器、六项哲学、不可妥协项 || Why it exists, why the orchestration layer, why a self-built scheduler |
| 02 | [能力与边界 || Capabilities & Boundaries](02-capabilities-boundaries.md) | 能做什么（6 类能力）+ 能力边界（Non-Goals/前提/理论上限/成熟度缺口）|| What it can do + boundaries |

### 第二部分 · 工作原理 || Part II · How It Works

| # | 文档 || Document | 内容 || Content |
|---|---|---|
| 03 | [整体架构 || Architecture](03-architecture.md) | 三层架构、数据流、48 模块地图、五图谱、熔断/检查点/审计链 || Three-layer model, data flow, 48-module map, five graphs |
| 04 | [端到端流程 || End-to-End Workflow](04-workflow.md) | 三种宏观模式、真实状态机、全生命周期 11 阶段、全景时序图 || Three modes, real state machine, 11-stage lifecycle |
| 05 | [方法论与理论 || Methodology & Theory](05-methodology-theory.md) | 52 个理论挂载点、11 个学术领域、每环节方法论映射 || 52 theory mount-points across 11 fields |
| 06 | [九层防幻觉 || Hallucination Defense](06-hallucination-defense.md) | L1–L9 逐层原理、执行管道、四类幻觉打击、效果数据 || Layer-by-layer L1–L9, pipeline, effectiveness |

### 第三部分 · 使用与扩展 || Part III · Use & Extend

| # | 文档 || Document | 内容 || Content |
|---|---|---|
| 07 | [技术方案 || Technical Design](07-technical-stack.md) | 技术栈矩阵、LiteLLM 网关与三层路由、沙箱、存储、可观测性 || Stack, gateway, sandbox, storage, observability |
| 08 | [使用说明 || Usage Guide](08-usage-guide.md) | 三种启动方式、配置项、CLI、前端页面、主用户工作流 || Launch modes, config, CLI, screens, workflow |
| 09 | [API 参考 || API Reference](09-api-reference.md) | 全部路由组、代表端点、WebSocket/SSE 通道 || All route groups, endpoints, channels |
| 10 | [再开发说明 || Development Guide](10-development-guide.md) | 四阶段工作流、模块职责表、测试体系、exe 构建链路、贡献约定 || Four-stage workflow, testing, build chain |
| 11 | [附录 || Appendix](11-appendix.md) | 术语表、核心指标基线、路线图、原始设计文档索引 || Glossary, baselines, roadmap, source-doc index |

---

## 一句话理解 Orbit || Orbit in One Sentence

Orbit 不是"再造一个 Claude Code"，而是站在 Claude Code / Codex 之上的治理层——让一群 AI Agent 协作完成软件开发全流程，并对每一步做编排、验证、追溯。 || Orbit is not "another Claude Code" — it is the governance layer above single-agent coders. It lets a fleet of AI agents collaborate through the full software-development lifecycle while orchestrating, validating, and tracing every step.

四个动词是全书主线： || Four verbs run through this whole manual:

| 编排 || Orchestrate | 治理 || Govern | 验证 || Validate | 追溯 || Trace |
|---|---|---|---|
| 自研 asyncio 状态机调度器 || Self-built asyncio state-machine scheduler | 五图谱 + 权限 + 资源熔断 || Five graphs + permissions + resource breaker | 9 层防幻觉纵深防御 || 9-layer defense-in-depth | `task_audit_trail` 审计链 || The `task_audit_trail` audit chain |

---

## 文档约定 || Conventions

- 每个标题、段落、列表项、表格单元格均"中文在上、英文小一号紧贴其下"。 || Every heading, paragraph, list item, and table cell shows Chinese on top with smaller English directly beneath.
- 凡涉及具体实现，均标注源文件路径（`src/orbit/...`）或设计文档，便于回溯核对。 || Every concrete claim cites a source file (`src/orbit/...`) or design doc for verification.
- 数据/指标以撰写时仓库状态为准；以 [`docs/产品路线图.md`](../产品路线图.md) 与 [`docs/已实现功能清单.md`](../已实现功能清单.md) 为权威更新源。 || Metrics reflect repo state at writing time; the roadmap and feature-list docs are the authoritative live sources.
- HTML 版由 `scripts/render_manual.py` 从 Markdown 生成，重生成命令：`python scripts/render_manual.py`。 || The HTML build is generated from Markdown by `scripts/render_manual.py`; regenerate with `python scripts/render_manual.py`.

## 相关文档 || Related Docs

- [`README.md`](../../README.md) — 项目根 README（快速开始） || Root README (quick start)
- [`AGENTS.md`](../../AGENTS.md) — 开发哲学与实现约束全集 || Full development philosophy and implementation constraints
- [`docs/charter.md`](../charter.md) — 项目章程（度量基线、范围、风险 — 本项目"宪法"）|| Project charter (baselines, scope, risks — the "constitution")
- [`docs/开发计划_V14.1.md`](../开发计划_V14.1.md) — 总体设计（26 章，指向 `docs/开发计划/` 子文档）|| Overall design (26 chapters)
- [`docs/WORKFLOW.md`](../WORKFLOW.md) — 四阶段开发流程细则 || Four-stage development workflow details
- [`docs/三层架构规范.md`](../三层架构规范.md) — 三层边界与静态检查规则 || Three-layer boundaries and static-check rules
</content>
