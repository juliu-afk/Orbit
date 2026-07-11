# 05 · 方法论与理论映射 || Methodology & Theory Map

[← 返回目录 || Back to index](README.md) · [← 上一章：端到端流程 || Prev: End-to-End Workflow](04-workflow.md)

> Orbit 每个环节都锚定一个可验证的学术方法，而非拍脑袋。本章系统列出全部 **52 个理论/方法论挂载点**，跨 11 个学术领域。研究者重点章节。每行标注：环节 · 理论(提出者/年) · 一句话 · 源文件。 || Every Orbit mechanism is anchored to a verifiable academic method, not guesswork. This chapter systematically lists all **52 theory/methodology mount-points** across 11 fields. A key chapter for researchers. Each row: mechanism · theory (author/year) · one-liner · source file.

---

## 5.1 全景：11 个学术领域 || Overview: 11 Academic Fields

| 领域 || Field | 代表方法 || Representative methods |
|---|---|
| 强化学习 || Reinforcement Learning | MCTS · GRPO · Thompson Bandit |
| 因果推理 || Causal Inference | Pearl SCM · DoWhy GCM · do-calculus |
| 形式化方法 || Formal Methods | Z3 SMT · Hoare Logic · LTL Model Checking · Separation Logic |
| 信息论 || Information Theory | Shannon Entropy · Information Bottleneck · Minimum Description Length |
| 博弈论与机制设计 || Game Theory & Mechanism Design | VCG · Shapley Value · BFT Consensus |
| 几何方法 || Geometric Methods | Information Geometry (Fisher-Rao) · Spectral Graph Theory · Optimal Transport |
| 控制理论 || Control Theory | PID Control · Circuit Breaker |
| 机器学习理论 || ML Theory | PAC Learning · Differential Privacy |
| 编程语言理论 || PL Theory | Abstract Interpretation · Type Systems · Algebraic Effects · Program Slicing |
| 认知科学 || Cognitive Science | ReAct · ReflAct · Metacognition · Free Energy Principle |
| 科学方法 || Scientific Method | Ablation Study |

## 5.2 按环节的方法论 || Methodology by Mechanism

### 5.2.1 Agent 执行层 || Agent Execution

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| ReActAgent | ReAct (Google, 2023) | Think→Act→Observe 循环，推理与工具调用交替 || Interleaves reasoning and tool calls | `agents/react_agent/agent.py` |
| MCTSPlanner | MCTS + UCB1 (Coulom 2006 / Kocsis-Szepesvári 2006) | 蒙特卡洛树搜索并行探索多推理路径，对标 Tree-of-Thought || Parallel path search | `agents/mcts.py` |
| PreActEngine | PreAct (ICLR 2025) | Action 前用双预测器估成功率/风险，高风险则改道减少回滚 || Predicts risk before acting | `agents/preact.py` |
| ReflectionEngine | ReflAct / AgentDebug (2025) | 每步 Observation 后结构化反思，检测目标漂移 || Structured post-step reflection | `agents/reflection.py` |
| AgentMDP | MDP / Bellman (1957) | 将 Agent 循环形式化为有限时域 MDP，算 Bellman gap || Formalizes loop as an MDP | `agents/mdp.py` |
| BisimulationChecker | Bisimulation (Milner, 1989) | 比较两 LTS 行为等价，判断策略能否无损替换 || Behavioral equivalence of policies | `agents/bisim.py` |

### 5.2.2 自进化与对齐 || Self-Evolution & Alignment

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| DistillationEngine | EvolveR (2025) | 从轨迹离线蒸馏可复用策略原则（失败→避免，成功→复用）|| Offline principle distillation | `evolution/distill.py` |
| GEPAEngine | GEPA (ICLR 2026 Oral) | 遗传算法进化 Prompt：变异/交叉 + Pareto 兼顾准确率与 Token || Genetic-Pareto prompt evolution | `evolution/gepa.py` |
| GRPOScorer | GRPO (Group Relative Policy Optimization) | 对比原则应用前后成功率 delta 调效用 + 自动剪枝 || Relative scoring + pruning | `evolution/grpo.py` |
| ScopeMemory | SCOPE (arXiv 2512.15374) | 双流记忆：战术(临时) + 战略(持久)，3+ 任务复现自动升级 || Dual-stream memory promotion | `evolution/scope.py` |
| AnchorGuard | ANCHOR (Alignment Tipping) | 蒸馏/应用前后注入监督检查点，防自进化触发对齐崩溃 || Alignment guardrails | `evolution/anchor.py` |
| PACBound | PAC Learning (Valiant, 1984) | 泛化误差上界 ε=√((ln|H|+ln(1/δ))/2m) 替代硬编码阈值 || Sample-adaptive threshold | `evolution/pac_bounds.py` |
| InfoGeometry | Information Geometry / Fisher-Rao (Amari, 1998) | Fisher 对角近似下自然梯度，参数化不变的最陡下降 || Natural-gradient descent | `evolution/info_geom.py` |

### 5.2.3 因果推理 || Causal Inference

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| RootCauseAnalyzer | Pearl Hierarchy / do-calculus + DoWhy GCM (Pearl 2009) | 因果图上 Shapley 对称归因，区分起源节点与继承节点 || Causal anomaly attribution | `causal/root_cause.py` |
| CausalModelManager | SCM / DoWhy Structural Causal Model | 从领域知识建因果 DAG，用可逆 SCM 拟合边权 || Fits an SCM from traces | `causal/graph.py` |

### 5.2.4 防幻觉 L1–L10 || Anti-Hallucination L1–L10

| 层 || Layer | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| L1 图谱 || Graph | 静态分析 / AST 符号解析 || Static analysis | ast 提符号在 CodeGraph 验存在性 || Symbol existence | `hallucination/l1_graph.py` |
| L2 追踪 || Trace | 动态分析 / sys.settrace || Dynamic analysis | 沙箱注入 settrace 比对调用 || Runtime call tracing | `hallucination/l2_dynamic.py` |
| L3 熵 || Entropy | Shannon Entropy (1948) | 逐 token 归一化熵，超阈判"猜" || Per-token entropy | `hallucination/l3_entropy.py` |
| L4 类型 || Type | Type Theory / Hindley-Milner | mypy --strict 类型一致性 || Static typing | `hallucination/l4_type.py` |
| L5 Z3 | SMT / Z3 (de Moura-Bjørner 2008) + Hoare Logic | @formal pre/post 构 Z3 公式求反例 || SMT proof of contracts | `hallucination/l5_z3.py` |
| L6 合约 || Contract | Design-by-Contract (Meyer, 1992) | prance 解析 OpenAPI 逐端点比对 || Contract conformance | `hallucination/l6_contract.py` |
| L7 沙箱 || Sandbox | 运行时验证 / 测试执行 || Runtime validation | 沙箱跑代码 + 断言 || Sandbox execution | `hallucination/l7_runtime.py` |
| L8 配置 || Config | SHA256 指纹比对 || Fingerprint diff | 与黄金基线比对，漂移告警/修复 || Drift detect | `hallucination/l8_config.py` |
| L9 时序 || Temporal | LTL Model Checking (Pnueli, 1977) | 自实现 LTL 检查器验状态机安全性(G)/活性(F) || State-machine LTL check | `hallucination/l9_temporal.py` |
| L10 分离 || Separation | Separation Logic (Reynolds/O'Hearn, 2002) | 堆所有权 + 别名分析 + Frame 条件 || Memory-safety check | `hallucination/l10_separation.py` |
| 抽象解释 || Abstract Interp | Abstract Interpretation / Galois (Cousot 1977) | 分析层间抽象域依赖，L1 失败影响 L4/L7 可靠性 || Inter-layer soundness | `hallucination/abstract_interp.py` |
| 效应追踪 || Effect Tracker | Algebraic Effects (Plotkin-Pretnar, 2009) | AST 分析 async/io/state 效应，检并发竞赛 || Effect-based race detect | `hallucination/effect_tracker.py` |

> 说明：代码实现到 L10 + 抽象解释/效应追踪，比设计口径"9 层"更深；"9 层防幻觉"是设计层命名，L9=动态合规在 `compliance/`。详见 [06 九层防幻觉](06-hallucination-defense.md)。 || Note: the code goes beyond the "9-layer" design label — implementing up to L10 plus abstract interpretation and effect tracking; "L9 dynamic compliance" lives in `compliance/`. See [06 Hallucination Defense](06-hallucination-defense.md).

### 5.2.5 上下文与压缩 || Context & Compression

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| CascadePruner | SWE-Pruner 级联 (mechanical>semantic>LLM) | 4 阶段破坏性递增裁剪，每级检查预算 || Cascaded pruning | `compression/cascade.py` |
| IBCompressor | Information Bottleneck (Tishby, 1999) + 0-1 Knapsack | min I(X;C)-βI(C;Y)，背包内选最大互信息子集 || MI-maximizing selection | `compression/ib_compressor.py` |
| OTMatcher | Optimal Transport / Sinkhorn (Cuturi, 2013) | Sinkhorn 正则最优传输，Wasserstein 下最优上下文分配 || Optimal context assignment | `context/ot_matcher.py` |

### 5.2.6 路由与网关 || Routing & Gateway

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| RouterAgent | 多准则决策 || Multi-criteria decision | 5 维加权评分输出模型层 Tier 0–3 || Weighted tier scoring | `router/agent.py` |
| ThompsonBandit | Thompson Sampling (Thompson, 1933) | 每臂 Beta 后验采样，遗憾上界 O(√(kT ln T)) || Bandit model selection | `router/bandit.py` |
| CircuitBreaker | Circuit Breaker (Nygard, 2007) | 三态熔断，连续 5 失败/错误率>30% 触发 || 3-state breaker | `gateway/circuit_breaker.py` |
| RoutingStrategy | 成本-速度-质量权衡 || Cost-speed-quality | CHEAPEST/FASTEST/BEST_QUALITY 四策略 || Four routing strategies | `gateway/routing.py` |

### 5.2.7 元认知与自愈 || Metacognition & Self-Healing

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| MonitorAgent | Metacognitive Monitoring (AgentDebug, 2025) | 独立 Task 消费事件，规则优先 + LLM 兜底，fail-open || Secondary monitor agent | `metacognition/monitor.py` |
| PIDAgentController | PID Control | Kp/Ki/Kd 三元控制代替二元 HITL，减 60–80% 严重告警 || Smooth control correction | `metacognition/pid_controller.py` |
| FreeEnergyMonitor | Free Energy Principle (Friston, 2010) | 变分自由能 F=复杂度-精度+惊奇，统一各自进化模块 || Unifies via ΔF minimization | `metacognition/free_energy.py` |
| VigilSelfHealer | VIGIL (2025) | 失败库+诊断+修复三步，修根因而非回滚重试 || Observe-diagnose-repair | `metacognition/vigil.py` |

### 5.2.8 图谱理论 || Graph Theory

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| SpectralAnalyzer | Spectral Graph Theory (Chung, 1997) | 图拉普拉斯特征分解，Fiedler 值度量连通性 || Algebraic connectivity | `graph/spectral.py` |
| TDAAnalyzer | Persistent Homology (Edelsbrunner, 2002) | 持续同调 barcode + Betti 数量化拓扑 || Topological features | `graph/tda.py` |
| ProgramSlicer | Program Slicing (Weiser, 1984) | AST→CFG→DDG→PDG 前向/后向切片 || Forward/backward slicing | `graph/engines/slicer.py` |

### 5.2.9 博弈论、共识与隐私 || Game Theory, Consensus & Privacy

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| VCGAllocator | VCG / Mechanism Design (1961–1973) | Agent 报价分配子任务，诚实报价为占优策略 || Truthful task allocation | `compose/mechanism.py` |
| BFTGuard | Byzantine Fault Tolerance (Lamport et al., 1982) | n>3f；关键操作需 quorum=2f+1 共识 || Byzantine consensus | `goal/bft.py` |
| ShapleyAttribution | Shapley Value (Shapley, 1953) | n≤12 精确、n>12 蒙特卡洛，公平归因边际贡献 || Fair contribution attribution | `observability/attribution.py` |
| DPGuard | Differential Privacy (Dwork, 2006) | Laplace/Gaussian 机制加噪，ε-δ 防指标泄露 || Noise-added metrics | `observability/dp.py` |

### 5.2.10 检索、审查与效能 || Retrieval, Review & Effectiveness

| 机制 || Mechanism | 理论 || Theory | 一句话 || One-liner | 源文件 || Source |
|---|---|---|---|
| FTS + BM25 | BM25 (Robertson-Zaragoza, 2009) | 纯 Python BM25 + FTS5 + CJK bigram，零依赖全文搜索 || Zero-dep full-text search | `memory/fts.py` |
| MDLScorer | Minimum Description Length (Rissanen, 1978) | gzip 度量复杂度 + 测试惩罚，NSGA-II 式 Pareto 排序 || Complexity-based ranking | `review/mdl_scorer.py` |
| AblationContext | Ablation Study / 受控实验 || Controlled experiment | 临时禁模块测性能下降，ΔF1<0.03 降级 || Marginal-contribution measure | `effectiveness/ablation.py` |
| TaskShardingEngine | MapReduce / Data Parallelism | 按边界切分>8000 字符大任务并发合并 || Split-execute-merge | `sharding/engine.py` |

## 5.3 为什么用这些理论 || Why These Theories

理论不是装饰——每一个都服务于四大价值主张之一（见 [01 设计哲学](01-design-philosophy.md)）： || Theory is not decoration — each serves one of the four value propositions (see [01 Design Philosophy](01-design-philosophy.md)):

| 价值 || Value | 支撑理论 || Backing theories |
|---|---|
| 编排 || Orchestrate | MDP · MCTS · VCG 机制设计 · 最优传输 · Thompson Bandit（分配与选择的最优性）|| optimality of allocation & selection |
| 验证 || Validate | Z3/Hoare · LTL · 分离逻辑 · 抽象解释 · 类型论 · Shannon 熵（可证明或可量化的正确性）|| provable or quantifiable correctness |
| 追溯 || Trace | Pearl 因果 · Shapley 归因 · 差分隐私 · MDL（可解释、可归因、可保护的记录）|| explainable, attributable, protected records |
| 自进化 || Self-evolve | EvolveR · GEPA · GRPO · SCOPE · PAC · 信息几何 · 自由能原理（有理论保证的自我改进）|| self-improvement with theoretical guarantees |

核心信念：**用确定性的数学方法约束不确定的 LLM 输出**——这正是 Orbit"治理而非生成"哲学在每个环节的落地。 || Core belief: **constrain uncertain LLM output with deterministic mathematics** — the concrete embodiment of Orbit's "govern, not generate" philosophy at every step.

---

[← 返回目录 || Back to index](README.md) · [下一章：九层防幻觉 → || Next: Hallucination Defense →](06-hallucination-defense.md)
</content>
