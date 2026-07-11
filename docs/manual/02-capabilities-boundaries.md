# 02 · 能力与边界 || Capabilities & Boundaries

[← 返回目录 || Back to index](README.md) · [← 上一章：设计哲学 || Prev: Design Philosophy](01-design-philosophy.md)

> 本章回答"Orbit 能做什么、不能做什么"。使用者与决策者优先阅读。能力清单来自 [`docs/已实现功能清单.md`](../已实现功能清单.md)，边界均引自章程/PRD 的显式声明，非推测。 || This chapter answers "what Orbit can and cannot do". For users and decision-makers first. The capability list comes from [`docs/已实现功能清单.md`](../已实现功能清单.md); every boundary is cited from explicit statements in the charter/PRDs, not inferred.

---

## 2.1 能力清单 || Capabilities

### 2.1.1 代码开发编排 || Development Orchestration

| 能力 || Capability | 描述 || Description |
|---|---|
| 调度器状态机 || Scheduler state machine | 状态机驱动的多 Agent 开发全流程（IDLE→PARSING→SCOPING→PLANNING→CODING→VERIFYING→DONE） || State-machine-driven full multi-agent development flow |
| DAG 并行执行 || DAG parallel execution | 拓扑排序 + 分层并发 + 检查点恢复 || Topological sort + layered concurrency + checkpoint recovery |
| Goal 统一入口 || Goal unified intake | 自然语言 / PRD 文件 / 批量目录三态输入，自动清晰度判定 + 三层依赖检测 + 自主 PR 合入 || NL / PRD file / batch directory intake, auto clarity scoring + 3-tier dependency detection + autonomous PR merge |
| 8 角色 Agent 工厂 || 8-role Agent factory | Architect/Developer/Reviewer/QA/ConfigManager/Clarifier/Chatter/Dream（MCTS/PreAct 是执行引擎，非角色），按角色路由不同模型层 || 8 AgentRole enum members (MCTS/PreAct are engines, not roles), each routed to a model tier |
| 任务分片 || Task sharding | 大 PRD 按段落边界自动分片 + Semaphore 并发 || Large PRD auto-sharded on paragraph boundaries + semaphore concurrency |
| 需求澄清 || Requirement clarification | 完整性 + 矛盾检测 + 可行性评分（0–100），多轮生成结构化 PRD || Completeness + contradiction detection + feasibility score, multi-turn structured PRD |
| 高峰避让调度 || Off-peak scheduling | 按四大厂商高峰时段推迟非紧急任务 + 持久化延迟队列 || Defers non-urgent tasks by vendor peak windows + persistent delay queue |

### 2.1.2 五图谱记忆 || Five-Graph Memory

| 能力 || Capability | 描述 || Description |
|---|---|
| 代码图谱 || Code graph | Tree-sitter 解析 Python/TypeScript/SQL，调用链 + 继承 + 数据流（Def-Use），增量更新 || Multi-language parse, call/inheritance/data-flow chains, incremental |
| 数据库图谱 || DB graph | SQLAlchemy 反射 + 外键关系提取 || Reflection + foreign-key extraction |
| 配置图谱 || Config graph | 5 种格式 + SHA256 基线 + 漂移检测/自动修复 || 5 formats + SHA256 baseline + drift detection/auto-fix |
| 知识图谱 || Knowledge graph | 外挂领域本体（会计/金融/法律）+ BGE 向量搜索 + TF-IDF 降级 + MCP || Domain ontology + vector search + TF-IDF fallback + MCP |
| 元图谱 || Meta-graph | 12 种跨图谱关系 + 影响面分析 + 架构腐化检测 || 12 cross-graph relations + impact analysis + rot detection |
| 12 个 MCP 图谱工具 || 12 MCP graph tools | trace_path / search_code / dead_code / rename_symbol / safe_delete_symbol / type_hierarchy… || |
| 历史图快照 + 文件监视 || History snapshots + file watch | 按 git commit 建历史图 + watchdog 增量更新 || Per-commit history graph + watchdog incremental update |

### 2.1.3 防幻觉验证 || Anti-Hallucination

| 能力 || Capability | 描述 || Description |
|---|---|
| L1–L8 复合验证管道 || L1–L8 composite pipeline | 图谱/追踪/熵/类型/Z3/合约/沙箱/配置，CODING 后自动运行 || Runs automatically after CODING |
| L9 动态合规 || L9 dynamic compliance | 规则引擎 + 知识时效性检查 || Rule engine + knowledge timeliness check |
| 快速/全量两档 || Quick / full tiers | quick=L1+L4+L3 即时；full=L1–L8 完整 || quick for instant checks, full for completion |
| 消融实验量化 || Ablation quantification | 20 可消融目标，显式量化各层边际贡献（L1 ΔF1=+0.660） || Explicitly quantifies each layer's marginal contribution |

### 2.1.4 可观测与运维 || Observability & Operations

| 能力 || Capability | 描述 || Description |
|---|---|
| 驾驶舱实时监控 || Real-time cockpit | WebSocket 推送 DAG/Token/告警/健康评分 || Pushes DAG/token/alerts/health |
| AgentOps 体系 || AgentOps suite | Prometheus + 审计 + 告警 + 教训库 + Grafana/AlertManager || Metrics + audit + alerting + lessons + dashboards |
| Trace 链路追踪 || Distributed tracing | 7 模块 40+ span，异步批量 flush || 40+ spans across 7 modules |
| 资源熔断 || Resource guard | 令牌桶 + Token 预算 + 4 级降级 + 三态熔断（毫秒级） || Token bucket + budget + 4-level degradation + 3-state breaker |
| 元认知监控 + 自愈 || Metacognition + self-heal | 漂移/重复/延迟触发 + HITL + VIGIL 7 种失败模式自愈 || Drift/repeat/latency triggers + HITL + VIGIL self-healing |
| 备份/灾难恢复/版本注册 || Backup / DR / versioning | SQLite 快照 + SHA256 + CLI 恢复(list/verify/recover) + SOP || Snapshot + checksum + recovery CLI + SOP |

### 2.1.5 集成渠道 || Integration Channels

| 能力 || Capability | 描述 || Description |
|---|---|
| 微信通道 || WeChat channel | iLink Bot API 双向对话（命令/审批/通知）+ QR 绑定 || Bidirectional chat + QR binding |
| MCP 客户端桥 || MCP client bridge | JSON-RPC 2.0 over stdio，连接外部 MCP（如 Serena），工具自动发现 || Connects external MCP servers, auto tool discovery |
| MCP Server 对外暴露 || MCP server | 以 MCP 协议暴露 Orbit 内置工具供外部 Agent 调用 || Exposes Orbit tools to external agents |
| 桌面壳 || Desktop shell | 20MB Tauri 透明窗口，Vue3 驾驶舱 76 组件，Tailwind v4 || 20MB Tauri app, Vue3 cockpit |
| 代码依赖图可视化 || Dependency graph viz | Cytoscape.js 渲染（3 布局）+ 搜索 + 节点详情 || Cytoscape rendering + search + node detail |

### 2.1.6 自我进化 || Self-Evolution

| 能力 || Capability | 描述 || Description |
|---|---|
| GEPA Prompt 进化 || GEPA prompt evolution | 遗传 + 变异 + 交叉 + Pareto 筛选 || Genetic + mutation + crossover + Pareto |
| SCOPE 双流记忆 || SCOPE dual-stream memory | 战术（临时）+ 战略（持久）自动升级 || Tactical + strategic auto-promotion |
| 离线/LLM 蒸馏 || Offline / LLM distillation | 轨迹→策略原则（去重+评分+剪枝） || Trajectories → reusable principles |
| GRPO 评分 + ANCHOR 对齐 || GRPO scoring + ANCHOR alignment | 基线对比动态调效用 + 4 检查点防对齐崩溃 || Utility tuning + alignment guardrails |
| ReflAct 反思循环 || ReflAct reflection loop | 每轮 ReAct 后自评 + 漂移自动纠正 || Self-assessment + drift correction each turn |

---

## 2.2 能力边界 || Boundaries

> 以下每条均有源文件依据，是可验证的明确声明。 || Each item below is a verifiable, explicitly stated limit with a source.

### 2.2.1 明确 Non-Goals || Explicit Non-Goals

| 边界 || Boundary | 来源 || Source |
|---|---|
| 时序图谱、多集群联邦留待 V2 || Time-series graph & multi-cluster federation deferred to V2 | `charter.md:20-21` |
| 文档图谱仅设计、未实现代码 || Document graph is design-only, not implemented | `CLAUDE.md:52`；`产品路线图.md:121` |
| 防幻觉当前仅支持 Python（JS/TS 需扩展 Tree-sitter + tsc） || Anti-hallucination supports Python only | `PRD+ADR_4阶段.md:35` |
| L5 不验证 IO 密集/复杂循环；L6 不支持 gRPC；L8 不支持 K8s ConfigMap || L5/L6/L8 scope limits | `PRD+ADR_4阶段.md:93` |
| 代码图谱不支持 eval/exec/动态导入/控制流分析 || Code graph excludes dynamic features | `PRD+ADR_3阶段.md:8` |
| 数据库图谱仅关系型（PG/MySQL），不支持 NoSQL；仅单主库 || DB graph relational only, single primary | `PRD+ADR_3阶段.md:81,90` |
| 配置图谱不支持加密配置（sops） || Config graph excludes encrypted configs | `PRD+ADR_3阶段.md:124` |
| DAG 不支持运行时改拓扑/跨任务依赖；分片不支持跨语言 || DAG static, sharding single-language | `PRD+ADR_5阶段.md:8,515` |
| Agent 无状态（对话历史由调度器管理，Agent 间无工具调用链） || Agents are stateless | `PRD+ADR_5阶段.md:102` |
| 驾驶舱不含任务管理/历史回放/自定义仪表盘/移动端（均 V2） || Cockpit V2 scope-outs | `PRD+ADR_6阶段.md:660,998` |
| 知识图谱不自动演进（人工审核，Agent 只读） || Knowledge graph not auto-evolving | `PRD+ADR_Step3.4:14` |
| 自然语言交互仅查询/关联 Issue，不支持关闭等操作 || NL interaction is read-only on Issues | `PRD+ADR_自然语言交互与项目上下文.md:39` |

### 2.2.2 技术前提依赖 || Preconditions & Dependencies

| 依赖 || Dependency | 说明 || Note |
|---|---|
| Docker Engine ≥24 | 沙箱强制隔离，禁止宿主机直接执行 || Sandbox mandatory, no host execution |
| LiteLLM ≥1.40 | 所有 LLM 调用必经网关，禁止直连 provider || All LLM calls via gateway |
| LLM API Key + logprobs | L3 熵监控依赖 logprobs（部分模型不支持则降级） || L3 falls back without logprobs |
| Redis | 检查点热层；不可用时降级内存模式 || Degrades to memory if absent |
| Node.js 22+ | 微信通道（cc-weixin via npx），未装则不可用 || WeChat unavailable without it |
| PostgreSQL / MySQL | 数据库图谱反射目标 || DB graph reflection target |
| Rust 工具链（Tauri） | 桌面壳编译 || Desktop shell build |
| SQLite WAL 模式 | 图谱并发写串行化 || Serializes graph concurrent writes |

### 2.2.3 理论上限 || Theoretical Limits

| 上限 || Limit | 数值 || Value | 来源 || Source |
|---|---|---|
| 幻觉率门禁（非 0） || Hallucination gate (not 0) | <3% | `charter.md:8,65` |
| 静态分析理论天花板 || Static-analysis ceiling | 48.5–77% | 架构总览 §防幻觉 |
| 调度层延迟 || Scheduler latency | ≤1500ms | `charter.md:7` |
| 单任务 Token（暂缓硬门禁） || Token per task (gate deferred) | ≤35 | `charter.md:67` |
| Agent 循环硬上限 || Agent loop hard cap | 50 轮 + 步骤超时 120/180s || 50 turns + step timeout | `已实现功能清单.md:405` |
| 请求体上限 || Request body limit | 10MB | `api/main.py:154` |
| 上下文字段截断 || Context field truncation | 5000 chars/字段 || per field | `已实现功能清单.md:322` |
| L5 仅纯数学约束 || L5 pure-math only | 禁外部函数/副作用 || no external fns/side effects | `PRD+ADR_4阶段.md:116` |

### 2.2.4 当前成熟度缺口 || Current Maturity Gaps

| 缺口 || Gap | 数据 || Data | 来源 || Source |
|---|---|---|
| 测试覆盖率未达门禁 || Coverage below gate | 行 69% / 分支 ~60%，门禁 80% || line 69% vs 80% gate | `已实现功能清单.md:112-122` |
| pytest 未接入 CI || pytest not in CI | 仅 lint+typecheck 入 CI || only lint+typecheck gated | `已实现功能清单.md:116` |
| 部分防幻觉层埋点未全接线 || Some layers not fully wired | L4/L5/L6/L7 dag/task runner 埋点 || instrumentation gaps | `已实现功能清单.md:353` |
| Route 层覆盖率低 || Low route-layer coverage | 28 路由文件均值 43% || avg 43% | `已实现功能清单.md:136` |
| 集成测试偏少 || Few integration tests | 15 文件 || 15 files | `tests/integration/` |

### 2.2.5 未实现 / 仅设计态 || Not Implemented / Design-Only

| 项目 || Item | 状态 || Status | 来源 || Source |
|---|---|---|
| 文档图谱 DocGraph | 仅设计（pgvector+Neo4j 未落码） || design-only | `产品路线图.md:121` |
| 渐进式审查 ReviewCheckpoint | PRD→ADR→代码三列对照未实现 || not implemented | `开发计划/11:194` |
| 测试↔审查 L4 级联动 | asyncio.Queue 双向推送未实现 || not implemented | `开发计划/11:195` |
| 代码签名 || Code signing | SOP + 占位就绪，实际流程未实施 || placeholder only | `已实现功能清单.md:496` |
| 用户认证系统 || User auth | MVP 无认证，依赖反向代理 Basic Auth || no auth in MVP | `PRD+ADR_6阶段.md:660` |
| 单任务 Token 硬门禁 || Token hard gate | 设计 ≤35，暂缓 || deferred | `charter.md:67` |

---

[← 返回目录 || Back to index](README.md) · [下一章：整体架构 → || Next: Architecture →](03-architecture.md)
</content>
