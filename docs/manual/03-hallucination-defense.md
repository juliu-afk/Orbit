# 03 · 九层防幻觉 || 03 · Hallucination Defense

[← 返回目录 || Back to index](README.md) · [← 上一章 整体架构 || Previous: Architecture](02-architecture.md)

> Orbit 的验证内核。研究者重点章节。实现见 [`src/orbit/hallucination/`](../../src/orbit/hallucination/) 与 [`src/orbit/compliance/`](../../src/orbit/compliance/)。 || Orbit's verification kernel. Essential reading for researchers. See [`src/orbit/hallucination/`](../../src/orbit/hallucination/) and [`src/orbit/compliance/`](../../src/orbit/compliance/).

---

## 3.1 为什么需要 9 层 || Why Nine Layers

核心认知——**纯静态分析拦截幻觉的理论上限只有 48.5%–77%**。要把错误率压到 <3%，必须静态 + 动态结合，用"从快到慢"的分层管道：廉价层拦截大多数简单幻觉，昂贵层（沙箱执行）只处理残余高危幻觉。 || Static analysis alone caps at 48.5%–77% interception. To reach <3% error, Orbit combines static + dynamic checks in a "cheap-to-expensive" pipeline — cheap layers catch most simple hallucinations; expensive layers (sandbox execution) handle the residual high-risk ones.

分层成本逻辑（[`docs/开发计划/00-架构总览.md:540-544`](../开发计划/00-架构总览.md)） || Layered cost logic (see [`docs/开发计划/00-架构总览.md:540-544`](../开发计划/00-架构总览.md)):

| 层组 || Layer group | 拦截占比 || Interception share | 成本 || Cost |
|---|---|---|---|---|
| L1–L2 廉价层 || L1–L2 Cheap | ~80% 简单幻觉（语法、命名） || ~80% simple hallucinations (syntax, naming) | 接近零 || Near zero |
| L3–L4 中等层 || L3–L4 Medium | ~15% 复杂幻觉（语义、逻辑） || ~15% complex hallucinations (semantics, logic) | Token 放大 3–5×，仅关键路径 || Token amplification 3–5×, critical path only |
| L5–L7 高成本层 || L5–L7 High-cost | ~5% 高危幻觉 || ~5% high-risk hallucinations | 沙箱执行换效果 || Sandbox execution for effectiveness |
| L8–L9 把关层 || L8–L9 Gatekeeping | 配置一致性 + 合规时效性 || Config consistency + compliance timeliness | 零 Token / 异步 || Zero token / async |

## 3.2 四类幻觉与打击策略 || Four Hallucination Types

来源 [`docs/开发计划/00-架构总览.md:514-522`](../开发计划/00-架构总览.md) || Source: [`docs/开发计划/00-架构总览.md:514-522`](../开发计划/00-架构总览.md):

| 幻觉类型 || Hallucination type | 描述 || Description | 示例 || Example | 主打防御层 || Primary defense layers |
|---|---|---|---|---|---|---|---|
| **映射幻觉** || Mapping | 需求映射到错误 API/结构 || Requirement mapped to wrong API/structure | 需求"排序"→生成 `array_reverse()` || Requirement "sort" → generates `array_reverse()` | L3 + L6 |
| **命名幻觉** || Naming | 捏造不存在的函数/参数/库 || Fabricated non-existent functions/params/libraries | `pd.read_exel()` | L2 |
| **资源幻觉** || Resource | 引用不存在的文件/路径/资源 || References to non-existent files/paths/resources | `include 'config/missing.php'` | L5 + L7 |
| **逻辑幻觉** || Logic | 算法错误/边界遗漏/并发问题 || Algorithm errors / edge-case omissions / concurrency issues | 循环 `i <= count` 数组越界 || Loop `i <= count` array out-of-bounds | L4 + L5 |

## 3.3 逐层详解 || Layer-by-Layer

| 层 || Layer | 名称 || Name | 技术手段 || Approach | 拦截目标 || Target | 效果数据 || Effectiveness |
|---|---|---|---|---|---|---|---|---|---|
| **L1** | 图谱校验 || Graph Validation | CodeGraph 符号匹配 + JSON Schema/Pydantic 约束 || CodeGraph symbol matching + JSON Schema/Pydantic constraints | 语法级幻觉、引用不存在符号 || Syntax-level hallucinations, references to non-existent symbols | 99% |
| **L2** | 动态追踪 || Dynamic Tracing | AST 确定性匹配 + 沙箱运行时追踪（`__call`/`eval`/`call_user_func`） || AST deterministic matching + sandbox runtime tracing (`__call`/`eval`/`call_user_func`) | 命名幻觉、动态调用幻觉 || Naming hallucinations, dynamic call hallucinations | 检测 100%，召回 87.6%（F1=0.934），修复 77% || Detection 100%, recall 87.6% (F1=0.934), fix rate 77% |
| **L3** | 熵监控 || Entropy Monitoring | 采样一致性（3–5 候选 + MiniLM 相似度）+ 流式 Shannon 熵实时计算 || Sampling consistency (3–5 candidates + MiniLM similarity) + real-time streaming Shannon entropy | 语义级幻觉、高熵"胡言乱语" || Semantic hallucinations, high-entropy gibberish | AUROC=0.76，阈值 2.5 bits || AUROC=0.76, threshold 2.5 bits |
| **L4** | 类型检查 || Type Checking | mypy 静态类型检查 || mypy static type checking | 类型错误、API 签名不匹配 || Type errors, API signature mismatches | — |
| **L5** | Z3 形式化 || Z3 Formal Verification | rotalabs-verity CEGIS 循环（LLM 生成→Z3 验证→CE2P 修复→重生成），仅核心算法 || rotalabs-verity CEGIS loop (LLM generate → Z3 verify → CE2P repair → regenerate), core algorithms only | 逻辑幻觉、边界条件 || Logic hallucinations, edge cases | 99%（可证明），超时 5s，端到端 1.87–3.73s || 99% (provable), timeout 5s, end-to-end 1.87–3.73s |
| **L6** | 合约验证 || Contract Validation | 正向合约（PRD→Assertions）+ 反向分支覆盖检查 || Forward contracts (PRD → Assertions) + reverse branch-coverage check | 业务逻辑幻觉 || Business logic hallucinations | 零 Token || Zero token |
| **L7** | 沙箱执行 || Sandbox Execution | Docker 隔离执行，I/O 行为聚类（MIT 方法），多候选变体执行 + 最大簇 ≥70% 采纳 || Docker isolated execution, I/O behavior clustering (MIT method), multi-candidate variant execution + max cluster ≥70% acceptance | **所有类型（最强）** || **All types (strongest)** | 错误率 65%→2%（最优可至 0%） || Error rate 65%→2% (as low as 0% optimal) |
| **L8** | 配置漂移 || Config Drift | 黄金基线 SHA256 指纹比对，自动修复 || Golden-baseline SHA256 fingerprint comparison, auto-repair | 配置幻觉、环境不一致 || Config hallucinations, environment inconsistency | 零 Token，自动修复 || Zero token, auto-repair |
| **L9** | 动态合规 || Dynamic Compliance | 外部合规库实时查询 + 本地缓存，时效性判断 + 版本比对 + DSL 规则引擎 || External compliance database real-time query + local cache, timeliness check + version comparison + DSL rule engine | 过时知识引用、法规风险 || Outdated knowledge references, regulatory risks | 时效性 ≥95%，误报 ≤5%，延迟 P99<200ms || Timeliness ≥95%, false positive ≤5%, latency P99<200ms |

> L1–L8 枚举定义见 [`src/orbit/hallucination/schemas.py:15-25`](../../src/orbit/hallucination/schemas.py)；L9 为独立模块 [`src/orbit/compliance/validator.py`](../../src/orbit/compliance/validator.py)，设计见 [`docs/PRD+ADR_Step4.3_L9动态合规验证.md`](../PRD+ADR_Step4.3_L9动态合规验证.md)。 || L1–L8 enum definitions in [`src/orbit/hallucination/schemas.py:15-25`](../../src/orbit/hallucination/schemas.py); L9 is a standalone module at [`src/orbit/compliance/validator.py`](../../src/orbit/compliance/validator.py), see [`docs/PRD+ADR_Step4.3_L9动态合规验证.md`](../PRD+ADR_Step4.3_L9动态合规验证.md) for design.

## 3.4 执行管道 || Execution Pipeline

**关键**：管道**执行顺序**不等于层编号顺序。实际顺序为"从快到慢"（[`src/orbit/hallucination/pipeline.py:43-52`](../../src/orbit/hallucination/pipeline.py)）： || **Key**: The pipeline **execution order** is NOT the layer number order. The actual order is "cheapest-first" (see [`src/orbit/hallucination/pipeline.py:43-52`](../../src/orbit/hallucination/pipeline.py)):

```
L1 图谱 → L4 类型 → L3 熵 → L2 追踪 → L6 合约 → L8 配置 → L7 沙箱 → L5 Z3
                                                            ↓
                                                       L9 合规（独立）
```

两种调用入口： || Two invocation entry points:

| 入口 || Entry | 层组合 || Layer combination | 用途 || Purpose |
|---|---|---|---|---|
| `validate_quick()` | L1 + L4 + L3 | 每次代码生成后即时检查 || Instant check after each code generation |
| `validate_full()` | L1–L8 全量 || L1–L8 full | coding 阶段完成后完整验证 || Full validation after coding phase completes |

### 致命层熔断（FATAL_LEVELS） || Fatal Layer Early Termination (FATAL_LEVELS)

**L1 图谱** 和 **L7 沙箱** 运行时失败时，管道**立即停止**，不再执行后续层——因为这两层失败意味着代码根本不可信，继续验证无意义（[`pipeline.py:55-58`](../../src/orbit/hallucination/pipeline.py)）。 || When **L1 Graph** or **L7 Sandbox** fails at runtime, the pipeline **halts immediately** and does not execute subsequent layers — failure in these two layers means the code is fundamentally untrustworthy, making further validation meaningless (see [`pipeline.py:55-58`](../../src/orbit/hallucination/pipeline.py)).

## 3.5 设计原理小结 || Design Rationale

1. **顺序服务于早停**：便宜且高召回的层放前面，一旦发现致命问题即提前终止，省下昂贵层的开销。 || **Order serves early termination**: cheap, high-recall layers go first. Once a fatal problem is detected, the pipeline terminates early, saving the cost of expensive layers.
2. **静动互补**：L1/L4/L5/L6/L8 静态（确定性、可证明），L2/L3/L7 动态（运行时真值）。静态给出必要条件，动态给出充分验证。 || **Static-dynamic complementarity**: L1/L4/L5/L6/L8 are static (deterministic, provable), L2/L3/L7 are dynamic (runtime ground truth). Static provides necessary conditions, dynamic provides sufficient verification.
3. **L7 沙箱是最后防线**：能拦截所有类型幻觉，把错误率从 65% 压到 2%，代价是 Docker 执行开销——因此只在 full 验证跑。 || **L7 Sandbox is the last line of defense**: it catches all hallucination types, reducing error rate from 65% to 2%, at the cost of Docker execution overhead — hence it only runs in full validation.
4. **L9 独立于 L1–L8**：合规是"知识时效"维度，与代码正确性正交，故单独成模块、异步执行、不阻塞主管道。 || **L9 is independent from L1–L8**: compliance is a "knowledge timeliness" dimension orthogonal to code correctness, so it lives as a separate module, runs asynchronously, and does not block the main pipeline.

---

[← 返回目录 || Back to index](README.md) · [下一章：技术方案 → || Next: Technical Design →](04-technical-stack.md)
