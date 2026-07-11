# 02 · 整体架构 · Architecture

[← 返回目录 Back to index](README.md) · [← 上一章 设计哲学](01-design-philosophy.md)

> 本章描述 Orbit 的骨架：三层通信边界、任务数据流、48 模块地图、五图谱体系、熔断/检查点/审计链。开发者与研究者共读。

---

## 2.1 三层架构规范 · The Three-Layer Model

**中文**：Orbit 把所有交互严格分成三层，边界不可跨越。这是保证"可审计、不失控"的结构基础。

**English**: All interactions fall into three strictly separated layers with non-crossable boundaries — the structural basis for auditability.

```
Layer 1  系统 → Agent      协程拉起      (asyncio)      scheduler/orchestrator.py :: _run_agent()
Layer 2  Agent → 工具      MCP           (tool call)    agents/base.py :: act() → ToolRegistry.invoke()
Layer 3  Agent → Agent     A2A           (message bus)  communication/message_bus.py :: request()
```

| 层 | 协议 | 数据 | 关键约束 |
|---|---|---|---|
| **L1 系统→Agent** | Python asyncio 协程（非网络） | `TaskContext`(L1–L5 五层上下文) → `AgentResult` | 调度器不直接调 MCP 工具或 MessageBus |
| **L2 Agent→工具** | MCP (Model Context Protocol) | 工具调用请求/响应 | 权限/限流/版本由 ToolRegistry 统一管理 |
| **L3 Agent→Agent** | A2A via MessageBus | 4 模式：Request-Response / Notification / Streaming / Callback | Agent 间禁止直接调 `run()`，必须走 MessageBus |

### 静态检查 4 条硬规则（[`docs/三层架构规范.md:1-72`](../三层架构规范.md)）

1. Orchestrator 中不得出现 `mcp_client` 或 `ToolRegistry.invoke()`。
2. Agent 基类中不得出现 `asyncio.create_task()` 拉起其他 Agent 协程。
3. Agent 间通信必须走 `MessageBus`，禁止直接调用其他 Agent 的 `run()`。
4. 外部系统不直接与 Agent 交互，必须经 REST API → Orchestrator。

## 2.2 任务数据流全链路 · End-to-End Data Flow

一个需求从进入到交付，经过的完整链路：

```
用户需求(NL/PRD)
   │  REST POST /api/v1/goal  或  WebSocket /chat
   ▼
IntakeRouter 意图判定 ──▶ ClarifierAgent 多轮澄清 ──▶ 结构化 PRD
   ▼
Scheduler 状态机  PARSING → PLANNING → CODING → VALIDATING → DONE
   │   每个转换点存 Checkpoint（Redis 热 + PostgreSQL 冷）
   ▼
Agent 5 角色协作（Architect → Developer → Reviewer → QA → ConfigManager）
   │   L2: 经 ToolRegistry 调工具   L3: 经 MessageBus 互相通信
   ▼
生成代码 ──▶ 9 层防幻觉管道（quick: L1+L4+L3 / full: L1–L8 → L9）
   │   任一致命层(L1图谱/L7沙箱)失败 → 立即停止 + 回滚检查点
   ▼
五图谱读写（代码/数据库/配置/知识/元图谱，统一 query_graph()，<50ms）
   ▼
审计链记录（task_audit_trail：状态转换 + LLM 调用摘要 + 验证结果）
   ▼
交付（PR 合入 / 报告 / 可观测性看板）
```

## 2.3 模块地图 · Module Map

`src/orbit/` 下 48 个包 + `launcher.py`。粗体为核心模块。

### 治理内核 · Governance Core

| 模块 | 职责 |
|---|---|
| **scheduler** | 任务调度器——状态机、检查点、回滚、并发控制 |
| **hallucination** | 防幻觉 L1–L8 纵深防御（图谱验证→动态追踪→熵监控→类型检查→Z3→合约→沙箱→配置漂移） |
| **compliance** | L9 动态合规验证——知识时效性检查 + 规则引擎 |
| **checkpoint** | 调度器检查点持久化（Redis 热 + PostgreSQL 冷，四级降级） |
| **resource_guard** | 资源熔断——令牌桶 + Token 预算 + 多级降级 + 三态机 |
| **sandbox** | 沙箱隔离执行——DockerSandbox（主）/ ProcessSandbox（兜底）自动选择 |
| **security** | 5 层 deny-wins 权限引擎（agent_role→tool_category→path_scope→sandbox→global_deny） |

### 图谱与知识 · Graphs & Knowledge

| 模块 | 职责 |
|---|---|
| **graph** | 代码图谱——CodeGraph SQLite + Tree-sitter 多语言解析；元图谱 12 种跨图谱关系 |
| **knowledge** | 外挂领域知识图谱——SQLite + BGE 向量搜索 + TF-IDF 降级 + MCP |
| **causal** | 因果推理引擎——CausalGraph、RootCauseAnalyzer、因果推荐 |
| memory | 文件记忆系统——MEMORY.md 读写 + FTS5 全文搜索 + BM25 评分 |

### Agent 与编排 · Agents & Orchestration

| 模块 | 职责 |
|---|---|
| **agents** | 5 核心角色（Architect/Developer/Reviewer/QA/Clarifier）+ ReActAgent 循环 |
| **gateway** | LLM 网关——LiteLLM 封装，三层模型路由（T1/T2/T3）+ 降级 |
| **compose** | Compose 流水线——spec-driven 多 Agent 编排（SKILL.md→Parser→Orchestrator） |
| **communication** | Agent 通信协议——MessageBus 4 模式 + 幂等 + 熔断传播 |
| **goal** | Goal 模式——多独立会话编排 + 自主 PR 合入（ProcessGuard/MetaOrchestrator/CritiqueAgent/Ensemble/Verifier） |
| goal_judge | 目标达成判定——Verdict schema + fail-open + MAX_GOAL_REACT 硬上限 |
| loop | Loop 模式——定时重复执行 Goal/命令（CronParser + LoopScheduler） |
| router | 智能路由——RouterAgent 评估复杂度 → 模型级别推荐 → CC_SWITCH 强制覆盖 |
| sharding | 动态任务分片——大任务自动拆分（Token 预估 + 边界识别 + 并发调度 + 结果合并） |
| actors | 子 Agent 生命周期——ActorRegistry(SQLite 状态机)、Spawn、Watchdog（zombie 清理） |
| modes | Mode File System——grill-me 交互协议层，YAML 定义 Agent 行为 |

### 上下文与自进化 · Context & Evolution

| 模块 | 职责 |
|---|---|
| context | 上下文匹配引擎——NL→关键词→项目匹配→预构建器 + 扫描器 |
| compression | 上下文压缩——8-step 算法 + 5-layer 管线 + CascadePruner 级联裁剪 + Token 预算 |
| prompt | Prompt 构建器——stable/context/volatile 三层拼接 |
| evolution | 自进化与对齐——离线自蒸馏、GRPO 评分、GEPA Prompt 进化、SCOPE 双流记忆 |
| dream | 自进化模块——5 阶段 LLM 合并 + 去重 + 验证 + 7 天自动触发 |
| metacognition | 元认知监控——独立 asyncio Task 消费 StreamEvent，目标漂移/重复/延迟检测 + HITL 移交 |
| testing | Agent 测试自循环——五层内循环（意图理解→生成→TDD→沙箱→反馈） |
| effectiveness | 模块效能测量——消融实验（AblationContext）+ benchmark 运行器 |

### 平台与接口 · Platform & Interface

| 模块 | 职责 |
|---|---|
| **api** | FastAPI 应用——路由注册（30+ 端点文件）、中间件 |
| **observability** | AgentOps 可观测性——Prometheus 指标 + 审计日志 + 告警引擎 + Trace 链路追踪 |
| ws | WebSocket——RFC 6455 驾驶舱实时推送 + ConnectionManager |
| stream | 流式模块——Agent 输出异步事件流 + SSE + CancellationToken |
| events | 事件总线——进程内发布-订阅，解耦调度器与 WebSocket 推送 |
| tools | 工具注册中心——权限隔离 + 滑动窗口限流 + 版本管理 + MCP 客户端 |
| sessions | 会话管理——Session + 聊天消息持久化（最小工作上下文单元） |
| projects | 项目注册表——项目元数据：名称/仓库/Issue 追踪器/标签 |
| brief | 项目说明书——LLM 驱动 Brief 生成、边界执行体系（BoundaryEngine）、基础代码包库 |
| review | 审查引擎——审查会话/决定/注释 CRUD（SQLAlchemy 2.0） |
| files | 文件服务——项目文件树、内容读取、diff 生成 |
| lsp | LSP 诊断代理——mypy/ruff 输出 → 标准化 Diagnostic |
| backup | 备份管理器——SQLite 快照 + SHA256 校验 + 恢复 |
| versioning | 版本注册表——版本追踪 + Schema 迁移 + 发布审计 |
| worktree | Git Worktree 隔离——多工作区管理（6 策略） |
| integration | 全模块集成接线——将独立模块接入 Agent 执行生命周期 |
| cli | CLI 入口——`orbit init-packages` / `orbit brief check` |
| core | 核心配置——Settings（Pydantic Settings） |
| infrastructure | DB 引擎、Session |
| launcher.py | PyInstaller 启动入口——隐式 import 所有路由模块 + `uvicorn.run` |

## 2.4 五图谱体系 · The Five-Graph System

**中文**：Orbit 的"全局记忆"由五张图谱构成，统一存于 CodeGraph SQLite，通过 `query_graph()` 本地查询（零 Token、<50ms）。

| 图谱 | 数据来源 | 核心价值 |
|---|---|---|
| **代码图谱** Code | 源码（Tree-sitter 解析） | 符号定义、调用关系、文件依赖、数据流 Def-Use 链 |
| **数据库图谱** DB | DDL + 存储过程 + 触发器 + 有条件 MVCC 快照 | 表结构、字段类型、主外键、索引、历史 Schema 版本 |
| **配置图谱** Config | .env + Nginx/Apache + PHP.ini + docker-compose | 环境变量依赖、运行时参数兼容性、容器资源限制 |
| **知识图谱** Knowledge | 外挂领域知识（会计/金融/法律） | 双模：精确查询（图谱）+ 语义检索（BGE RAG），经 MCP 暴露 |
| **元图谱** Meta | 五图谱间交叉引用（独立库 `data/meta_graph.db`） | 跨图谱关系、影响面分析、架构腐化检测、变更追溯 |

> 注：设计文档中还提到"文档图谱"，但**仅存在于设计，未落地代码**（[`CLAUDE.md:52`](../../CLAUDE.md)）。

### 元图谱 12 种跨图谱关系（[`src/orbit/graph/meta_graph.py:20-34`](../../src/orbit/graph/meta_graph.py)）

`READS_FROM` · `WRITES_TO` · `DELETES_FROM`（代码→数据库） · `DEPENDS_ON`（代码→配置/代码） · `OVERRIDES`（配置→配置） · `REFERENCES` · `COMPLIES_WITH`（代码→知识） · `PRODUCED_BY` · `MODIFIED_BY`（代码↔推理链） · `DECIDED_AT`（配置→推理链） · `CONNECTS_TO` · `USED_IN`（知识→代码）

### 元图谱能力

- **影响面分析**：`impact_analysis("PaymentService.process")` → `{databases, configs, knowledge, reasoning}`（[`meta_graph.py:125-157`](../../src/orbit/graph/meta_graph.py)）。
- **配置变更追溯**：`config_impact_trace("PAYMENT_TIMEOUT")` → 受影响代码 + 任务列表（`meta_graph.py:159-178`）。
- **架构腐化检测**：`architecture_health_check()` → 检测违反约束的关系，如"代码写数据库但无合规关联"（`meta_graph.py:180-213`）。

## 2.5 熔断 / 检查点 / 审计链 · Breaker / Checkpoint / Audit

### 2.5.1 熔断 Circuit Breaker

- 三态：`CLOSED` / `OPEN` / `HALF_OPEN`。
- 触发：Token 计数器超限 **或** 延迟超阈值 → 熔断并回滚到上一检查点。
- 决策延迟 ≤12ms（纯内存）。熵监控集成：流式响应实时算 Shannon 熵，>2.5 bits 触发重生成或熔断。
- 恢复：熔断后降级，拦截所有 LLM 请求；每 5 分钟放一个试探请求（半开），成功则逐步恢复。
- 实现：`resource_guard/resource_guard.py` + `gateway/circuit_breaker.py`（减熵已合并）。

### 2.5.2 检查点 Checkpoint（[`src/orbit/checkpoint/manager.py`](../../src/orbit/checkpoint/manager.py)）

- **双层冷热**：Redis（热，TTL=1h）+ PostgreSQL（冷备份）。
- **四级降级加载**：Redis → miss → PG → 回填 Redis → miss → 内存降级 → 磁盘文件兜底。
- **内容**：`task_id, state, retry_count, progress, context, updated_at, version`。
- **版本号乐观锁**：`WHERE version < EXCLUDED.version`，旧版本不能覆盖新版本。
- **保存时机**：每个关键状态转换点（PARSING→PLANNING→CODING→VALIDATING…）。
- **RTO 目标**：≤30 秒。

### 2.5.3 审计链 Audit Trail

- 表：`task_audit_trail`，记录每个状态转换、每次 LLM 调用摘要、每条验证结果。
- 链式结构：`parent_step_id` 递归追溯完整推理树。
- 存储成本：千次任务约 50MB（相比全量 MVCC 50GB，省 1000 倍）。
- 取舍：放弃完整回滚（<1% 场景，改由检查点提供），保留推理链追溯（100% 任务需要）。

---

[← 返回目录](README.md) · [下一章：九层防幻觉 →](03-hallucination-defense.md)
</content>
