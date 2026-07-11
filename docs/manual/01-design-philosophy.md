# 01 · 设计哲学 || Design Philosophy

[← 返回目录 || Back to index](README.md) · [← 上一章：总览 || Prev: Overview](00-overview.md)

> 本章回答"**为什么这么设计**"。研究者优先阅读。所有论断均可回溯至 [`docs/charter.md`](../charter.md)（项目"宪法"）与 [`docs/开发计划/00-架构总览.md`](../开发计划/00-架构总览.md)。 || This chapter answers "**why it is designed this way**" — preferred reading for researchers. Every claim is traceable back to [`docs/charter.md`](../charter.md) (the project "constitution") and [`docs/开发计划/00-架构总览.md`](../开发计划/00-架构总览.md).

---

## 1.1 核心命题：治理，而非生成 || Governance, Not Generation

Orbit 的根本命题是——LLM 生成代码的**能力**已经足够，缺的是让这种能力**可信、可控、可追溯**的治理体系。因此 Orbit 把重心放在"生成之后"和"生成之间"：多 Agent 如何协作、状态如何流转、幻觉如何拦截、决策如何追溯。 || Orbit's core thesis: LLMs are already *capable enough* at code generation; what's missing is a governance system that makes that capability **trustworthy, controllable, and traceable**. So Orbit invests in what happens *between* and *after* generation — how agents collaborate, how state transitions, how hallucinations are intercepted, how decisions are traced.

这解释了架构锚定声明的存在（[`charter.md:87-90`](../charter.md)）：任何把 Prompt 写成"你是一个 Python 专家"的执行层退化，都会被评审打回，因为它偏离了编排层的定位。 || This explains the architecture-anchoring assertion ([`charter.md:87-90`](../charter.md)): any regression to the execution layer — e.g., a prompt that reads "you are a Python expert" — is rejected at review because it deviates from the orchestration layer's mandate.

## 1.2 为什么锚定编排层 || Why the Orchestration Layer

单 Agent 工具（Claude Code / Codex）解决的是"一次生成质量"；Orbit 解决的是"**一群 Agent 跑完一个软件项目**"。两者不是竞争关系——Orbit 可以把单 Agent 工具当作执行节点，自己专注于上层治理： || Single-agent tools (Claude Code / Codex) solve "single-generation quality"; Orbit solves "**a fleet of agents completing a software project**". The two are not competitive — Orbit can use single-agent tools as execution nodes while focusing on upper-layer governance:

| 单 Agent 工具关心 || What single-agent tools care about | Orbit 关心 || What Orbit cares about |
|---|---|---|
| 这段代码写得好不好 || Is the code well-written | 谁来写、谁来审、谁来测、出错回滚到哪 || Who writes, reviews, tests, where to roll back on error |
| 单轮上下文塞什么 || What to fit in a single-turn context | 五图谱全局记忆、跨 Agent 上下文传递 || Five-graph global memory, cross-agent context passing |
| 生成结果 || Generation output | 生成过程的每一步可否被审计 || Whether every step of generation is auditable |

## 1.3 为什么自研调度器（而非 CrewAI）|| Why a Self-Built Scheduler (Not CrewAI)

现成多 Agent 框架（CrewAI 等）是黑盒，调度不可审计、Token 开销大、延迟高，与 Orbit 的"极致性能 + 透明可控"哲学冲突。基准对比（[`docs/开发计划/00-架构总览.md:83-91`](../开发计划/00-架构总览.md)）： || Off-the-shelf multi-agent frameworks (CrewAI, etc.) are black boxes — schedule non-auditable, high token cost, high latency — conflicting with Orbit's "extreme performance + transparent controllability" philosophy. Benchmark comparison ([`docs/开发计划/00-架构总览.md:83-91`](../开发计划/00-架构总览.md)):

| 维度 || Dimension | CrewAI | 自研调度器 || Self-built scheduler |
|---|---|---|---|
| 单任务 Token || Tokens per task | ~4.5K | ≤35（目标，可优化至 1/128）|| ≤35 (target, optimizable to 1/128) |
| 单次耗时（含验证）|| Latency per task (with validation) | ~32s | ~1.5s（目标）|| ~1.5s (target) |
| 内存 || Memory | ~200MB 框架开销 || ~200MB framework overhead | ~50MB |
| 可控性 || Controllability | 黑盒，难审计 || Black box, hard to audit | 完全可控、可修改 || Fully controllable and modifiable |

结论：**零黑盒依赖**是不可妥协项。所有调度逻辑用 Python asyncio 有限状态机自己实现，换来的是每个状态转换都能存检查点、能回滚、能审计。 || Conclusion: **zero black-box dependency** is non-negotiable. The entire scheduler is implemented as a Python asyncio finite-state machine, so every state transition can be checkpointed, rolled back, and audited.

## 1.4 六项设计哲学 || The Six Principles

来源 [`docs/开发计划/00-架构总览.md:72-78`](../开发计划/00-架构总览.md)： || Source [`docs/开发计划/00-架构总览.md:72-78`](../开发计划/00-架构总览.md):

| # | 哲学 || Philosophy | 含义 || Meaning |
|---|---|---|---|
| 1 | **极致性能** || **Extreme performance** | 单任务 Token ≤35，调度层延迟 ≤1.5s（不含验证层）|| ≤35 tokens/task, ≤1.5s scheduler latency (excluding validation layer) |
| 2 | **透明可控** || **Transparent & controllable** | 所有逻辑可审计、可修改，零黑盒依赖 || All logic auditable and modifiable, zero black-box dependency |
| 3 | **全维度覆盖** || **Full-dimension memory** | 代码+数据库+配置+知识+元图谱 = 五图谱完整记忆 || Code + DB + config + knowledge + meta-graph = full five-graph memory |
| 4 | **动静结合** || **Static + dynamic** | 确定性分析（Tree-sitter/Z3）+ 运行时反馈（追踪/熵监控）|| Deterministic analysis (Tree-sitter/Z3) + runtime feedback (tracing/entropy monitoring) |
| 5 | **渐进式复杂** || **Progressive complexity** | 先跑通核心闭环，再逐步优化，不追求一次性完美 || Run the core loop first, then optimize iteratively — no pursuit of one-shot perfection |
| 6 | **决策可追溯** || **Traceable decisions** | 每次动作、每个状态转换、每次验证均可追溯至原始上下文 || Every action, state transition, and validation traceable to the original context |

## 1.5 关键设计取舍 || Key Trade-offs

### 1.5.1 追溯 vs 完整回滚（审计链的取舍）|| Traceability vs Full Rollback (Audit Trail Trade-off)

Orbit 的审计链（`task_audit_trail`）**放弃了全量状态回滚**（低频，<1% 场景），**保留了推理链追溯**（高频，100% 任务需要）。代价对比：千次任务审计链约 50MB，而全量 MVCC 快照需 50GB——**节约 1000 倍存储**。回滚能力改由检查点（checkpoint）在关键状态点提供。 || Orbit's audit trail (`task_audit_trail`) **sacrifices full-state rollback** (low-frequency, <1% of scenarios) and **preserves inference-chain tracing** (high-frequency, needed by 100% of tasks). Cost comparison: ~50MB for 1000-task audit trails vs 50GB for full MVCC snapshots — **1000× storage savings**. Rollback is instead provided by checkpoints at key state points.

> 来源 [`docs/开发计划/00-架构总览.md:430-453`](../开发计划/00-架构总览.md)。 || Source [`docs/开发计划/00-架构总览.md:430-453`](../开发计划/00-架构总览.md).

### 1.5.2 静态分析的理论上限 || Theoretical Upper Bound of Static Analysis

核心认知：**纯静态分析拦截幻觉的理论上限只有 48.5%–77%**，必须与动态验证（沙箱执行、运行时追踪）结合，才能把错误率压到 <3%。这直接决定了 9 层防幻觉"从快到慢、静动结合"的分层结构（见 [06 防幻觉](06-hallucination-defense.md)）。 || Key insight: **the theoretical upper bound of pure static analysis for hallucination interception is only 48.5%–77%**; it must be combined with dynamic validation (sandbox execution, runtime tracing) to drive the error rate below 3%. This directly mandates the 9-layer hallucination defense's "fast-to-slow, static+dynamic" layered structure (see [06 Hallucination Defense](06-hallucination-defense.md)).

> 来源 [`docs/开发计划/00-架构总览.md:540-544,607-609`](../开发计划/00-架构总览.md)。 || Source [`docs/开发计划/00-架构总览.md:540-544,607-609`](../开发计划/00-架构总览.md).

## 1.6 不可妥协项 || Non-Negotiables

这些是架构"红线"，任何改动不得违反（来源 [`AGENTS.md:130-141`](../../AGENTS.md) + [`charter.md`](../charter.md)）： || These are architecture "red lines" that no change may violate (source [`AGENTS.md:130-141`](../../AGENTS.md) + [`charter.md`](../charter.md)):

| # | 红线 || Invariant | 理由 || Rationale |
|---|---|---|---|
| 1 | **锚定编排层** || **Anchor orchestration layer** | Prompt 必须为协作编排服务，退化为执行层则打回（Step 0.4）|| Prompts must serve collaborative orchestration; regression to execution layer is rejected (Step 0.4) |
| 2 | **零黑盒依赖** || **Zero black-box dependency** | 所有组件确定性可控、可审计、可修改 || All components deterministically controllable, auditable, modifiable |
| 3 | **LiteLLM 网关唯一入口** || **LiteLLM gateway as sole entry** | 禁止直连 provider——统一追踪 + 降级 || No direct provider connection — unified tracing + degradation |
| 4 | **Docker 沙箱强制** || **Docker sandbox mandatory** | LLM 生成代码不得在宿主机直接执行——安全基线 || LLM-generated code must not execute on the host machine — security baseline |
| 5 | **防幻觉链路完整性** || **Hallucination defense chain integrity** | 改防幻觉层不能只改一层——单层改动影响上下游判定 || Changes to the defense layer must not be isolated — single-layer changes affect upstream/downstream judgments |
| 6 | **调度器状态一致性** || **Scheduler state consistency** | 状态机改动必须全路径回归（转换/检查点/回滚）——否则任务卡死 || State-machine changes require full-path regression (transitions/checkpoints/rollback) — otherwise tasks stall |
| 7 | **密钥仅环境变量** || **Keys only via environment variables** | API key / Token 禁止硬编码 || API keys/tokens must not be hardcoded |
| 8 | **Charter 即宪法** || **Charter as constitution** | 架构决策争议时以 `charter.md` 为准 || `charter.md` prevails in architectural disputes |

---

[← 返回目录 || Back to index](README.md) · [下一章：整体架构 → || Next: Architecture →](03-architecture.md)
