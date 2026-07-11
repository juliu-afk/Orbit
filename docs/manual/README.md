# Orbit 说明书 · Orbit Manual

> 轻量级多 Agent 软件开发自循环系统 —— 完整说明书。
> A lightweight multi-agent self-looping software development system — complete manual.

本说明书面向三类读者，用一套带目录的文档覆盖 Orbit 的**设计哲学、整体架构、技术方案、使用说明、再开发说明**。
This manual serves three audiences and covers Orbit's **design philosophy, architecture, technical design, usage, and re-development** in one indexed set of documents.

| 读者 Reader | 你想知道 You want | 建议阅读顺序 Suggested path |
|---|---|---|
| 使用者 **User** | 怎么装、怎么跑、怎么用 | 00 → 05 → 06 |
| 开发者 **Developer** | 怎么改、怎么加功能、怎么构建 | 00 → 02 → 07 → 06 |
| 研究者 **Researcher** | 为什么这么设计、理论依据 | 01 → 02 → 03 → 08 |

---

## 目录 · Table of Contents

| # | 文档 Document | 内容 Content |
|---|---|---|
| 00 | [总览 · Overview](00-overview.md) | 项目定位、核心指标、技术栈全景、读者导航 |
| 01 | [设计哲学 · Design Philosophy](01-design-philosophy.md) | 为何存在、为何锚定编排层、为何自研调度器、六项哲学、不可妥协项 |
| 02 | [整体架构 · Architecture](02-architecture.md) | 三层架构规范、数据流全链路、48 模块地图、五图谱体系、熔断/检查点/审计链 |
| 03 | [九层防幻觉 · Hallucination Defense](03-hallucination-defense.md) | L1–L9 逐层原理、执行管道顺序、四类幻觉打击策略、效果数据 |
| 04 | [技术方案 · Technical Design](04-technical-stack.md) | 技术栈矩阵、LiteLLM 网关与三层路由、沙箱、存储、可观测性 |
| 05 | [使用说明 · Usage Guide](05-usage-guide.md) | 三种启动方式、配置项、CLI、前端页面、主用户工作流 |
| 06 | [API 参考 · API Reference](06-api-reference.md) | 全部路由组、代表端点、WebSocket/SSE 通道 |
| 07 | [再开发说明 · Development Guide](07-development-guide.md) | 四阶段工作流、模块职责表、测试体系、exe 构建链路、数据库迁移、贡献约定 |
| 08 | [附录 · Appendix](08-appendix.md) | 术语表、核心指标基线、路线图、原始设计文档索引 |

---

## 一句话理解 Orbit · Orbit in One Sentence

**中文**：Orbit 不是"再造一个 Claude Code"，而是**站在 Claude Code / Codex 之上的治理层**——让一群 AI Agent 协作完成软件开发全流程，并对每一步做**编排、验证、追溯**。

**English**: Orbit is not "another Claude Code" — it is the **governance layer above** single-agent coders. It lets a fleet of AI agents collaborate through the full software-development lifecycle, while **orchestrating, validating, and tracing** every step.

四个动词是全书主线 · Four verbs run through this whole manual:

| 编排 Orchestrate | 治理 Govern | 验证 Validate | 追溯 Trace |
|---|---|---|---|
| 自研 asyncio 状态机调度器 | 五图谱 + 权限 + 资源熔断 | 9 层防幻觉纵深防御 | `task_audit_trail` 审计链 |

---

## 文档约定 · Conventions

- 标题、关键术语中英对照；正文以中文为主，关键概念附英文摘要。
  Headings and key terms are bilingual; body text is Chinese-first with English summaries for core concepts.
- 凡涉及具体实现，均标注源文件路径（`src/orbit/...`）或设计文档，便于回溯核对。
  Every concrete claim cites a source file (`src/orbit/...`) or design doc for verification.
- 数据/指标以撰写时仓库状态为准，随版本演进；以 [`docs/产品路线图.md`](../产品路线图.md) 与 [`docs/已实现功能清单.md`](../已实现功能清单.md) 为权威更新源。
  Metrics reflect repo state at writing time; the roadmap and feature-list docs are the authoritative live sources.

## 相关文档 · Related Docs

- [`README.md`](../../README.md) — 项目根 README（快速开始）
- [`AGENTS.md`](../../AGENTS.md) — 开发哲学与实现约束全集
- [`docs/charter.md`](../charter.md) — 项目章程（度量基线、范围、风险 — 本项目"宪法"）
- [`docs/开发计划_V14.1.md`](../开发计划_V14.1.md) — 总体设计（26 章，指向 `docs/开发计划/` 子文档）
- [`docs/WORKFLOW.md`](../WORKFLOW.md) — 四阶段开发流程细则
- [`docs/三层架构规范.md`](../三层架构规范.md) — 三层边界与静态检查规则
</content>
</invoke>
