# 04 · 端到端流程 || End-to-End Workflow

[← 返回目录 || Back to index](README.md) · [← 上一章：整体架构 || Prev: Architecture](03-architecture.md)

> 本章叙述一个请求从进入到交付的完整生命周期，逐环节标注触发条件、负责模块（源文件）、做什么、产出。与 [03 整体架构](03-architecture.md) 的静态数据流互补——这里是动态时序。 || This chapter narrates the full lifecycle of a request from entry to delivery, annotating each step with its trigger, responsible module (source file), action, and output. It complements the static data flow in [03 Architecture](03-architecture.md) with a dynamic timeline.

---

## 4.1 三种宏观模式 || Three Macro Modes

| 模式 || Mode | 入口 || Entry | 编排器 || Orchestrator | 适用 || When |
|---|---|---|---|
| Goal 模式 || Goal mode | `POST /api/v1/goal` | `MetaOrchestrator`（`goal/meta_orchestrator.py`） | 高层目标含多子任务，自动拆解 + DAG + CritiqueGate + 自主 PR || High-level goal, multi-subtask |
| 单任务模式 || Single-task mode | WebSocket `/chat` 或 `POST /tasks` | `Scheduler`→`TaskRunner`（`scheduler/`） | 单 PRD 全流水线 || One PRD, full pipeline |
| Loop 模式 || Loop mode | `POST /api/v1/loop` | `LoopScheduler`（`loop/scheduler.py`） | 定期重复执行同一命令 || Periodic repetition |

## 4.2 真实状态机 || The Real State Machine

> 更正：早期文档误写 `PARSING→PLANNING→CODING→VALIDATING`。真实定义见 `scheduler/task_runner/checkpoint.py:23-37` 与 `api/schemas/task.py`。 || Correction: earlier docs mislabeled the states. The real definition is in `scheduler/task_runner/checkpoint.py:23-37` and `api/schemas/task.py`.

```
IDLE ─▶ PARSING ─▶ SCOPING ─▶ PLANNING ─▶ CODING ─▶ VERIFYING ─▶ DONE
 0%      10%        20%         30%         60%        85%         100%
                    │                                              ▲
        复杂度<30 走快车道 (FAST_LANE)：跳过 SCOPING/PLANNING/VERIFYING ──┘
终态: DONE / FAILED / CANCELLED
```

| 状态 || State | 角色 || Role | 做什么 || Action | 产物 || Output |
|---|---|---|---|
| IDLE | chatter | 初始，建检查点 || Initial, checkpoint | `CheckpointData(IDLE)` |
| PARSING | clarifier | 解析 PRD，提关键词，复杂度评分 || Parse PRD, keywords, complexity | `complexity_score, keywords` |
| SCOPING | 规则引擎（非 LLM） || rule engine | 确定性变更范围分析 || Deterministic scope analysis | `scope_analysis` |
| PLANNING | architect | 系统设计，多方案生成 || System design, multi-plan | `design_plan` |
| CODING | developer | ReAct 循环实现代码 || ReAct-loop implementation | `code_artifact` |
| VERIFYING | reviewer | 代码审查与验证 || Review & verify | `review_result` |
| DONE / FAILED / CANCELLED | — | 终态 || Terminal | 完整产物/错误 || Result/error |

快车道（`FAST_LANE_TRANSITIONS`：PARSING→CODING→DONE）由 `ComplexityScorer` 授权，LLM 无权绕过（`ProcessGuard.authorize_fast_lane()`）。 || The fast lane (`FAST_LANE_TRANSITIONS`: PARSING→CODING→DONE, skipping SCOPING/PLANNING/VERIFYING) is authorized only by `ComplexityScorer`; the LLM cannot bypass gates.

## 4.3 全生命周期 11 阶段 || The 11 Lifecycle Stages

### 阶段 0：请求入口 || Stage 0: Request Entry
四类入口——WebSocket 聊天（`chat.py:chat_endpoint`）、Goal REST（`goal.py:create_goal`）、任务 API（`tasks.py:create_task`）、Loop（`loop.py:create_loop`）。校验 token/workspace/并发冲突后创建会话或后台任务。 || Four entries validate token/workspace/concurrency, then create a session or background task.

### 阶段 1：意图路由与需求澄清 || Stage 1: Intent Routing & Clarification
`ChatterAgent`（`agents/chatter.py`）首触判定 `intent`：`chat` 直接回复；`programming` 转 `ClarifierAgent`（`agents/clarifier/agent.py`）多轮澄清，经 V1–V5 校验链（V1 字段完整/V2 一致性/V3 矛盾检测/V4 流式熵监控/V5 JSON schema）产出 `StructuredPRD`。用户 `confirm` 后建任务并 `spawn_task`。 || ChatterAgent routes intent; ClarifierAgent produces a StructuredPRD via the V1–V5 validation chain; on user confirm a task is spawned.

### 阶段 2：输入智能判定（Goal 模式）|| Stage 2: Intake Decision (Goal mode)
`IntakeRouter.route()`（`goal/intake_router.py`）检测输入形态 + 启发式评分清晰度/拆解度 → `IntakeDecision(needs_clarify, needs_decompose, is_batch)`。 || IntakeRouter scores clarity/decomposition and returns an IntakeDecision.

### 阶段 3：拆解与依赖分析（Goal 模式）|| Stage 3: Decomposition & Dependency (Goal mode)
按需澄清 → `PreFlightEstimator` 预估 → `GoalComposeBridge.generate_spec()` 生成含 `TaskDAG` 的 Spec → 用户确认。批量模式经 `DependencyAnalyzer.analyze()` 分层并发。 || Optional clarify → estimate → generate a Spec with a TaskDAG → user confirm; batch mode analyzes dependencies and runs layered concurrency.

### 阶段 4：调度器状态机 || Stage 4: Scheduler State Machine
单任务：`Scheduler.spawn_task()`→`TaskRunner.run_task()` 按 §4.2 状态机推进，每轮 `_agent_cycle`→`_run_agent`→`_transition`→`_save_checkpoint`。Goal 子任务：`SubTaskSession.run_full_pipeline()` + `ProcessGuard` 门禁 + 独立 git 分支 `goal/{goal_id}/{task_id}` 隔离。 || Single-task advances the state machine per §4.2; Goal subtasks run through ProcessGuard gates in isolated git branches.

### 阶段 5：Agent 执行 || Stage 5: Agent Execution
`AgentFactory.create()`（`agents/factory.py`）按角色建实例并绑定模型层（architect=T3 GLM-5.2，developer=T2 DS V4 Pro 失败升 T3，clarifier/chatter=T1 Flash）。`TaskRunner._run_agent` 注入能力引擎：ReflectionEngine(ReflAct)、PreActEngine、VigilSelfHealer、MCTSPlanner（仅 architect）。`ReActAgent` 在 `write_file/edit_file` 后自动调 `validate_quick` 快速防幻觉（fail-open）。 || The factory binds each role to a model tier and injects Reflection/PreAct/VIGIL/MCTS engines; ReActAgent runs quick anti-hallucination after each file write.

### 阶段 6：批判门禁（Goal 模式）|| Stage 6: Critique Gate (Goal mode)
CODING 完成后 `CritiqueAgent.critique()`（`goal/critique.py`）跨模型族审查（仅看代码产物 + 验证结果，不看生成推理），四维评分（正确性 40%/安全 25%/性能 15%/可维护 20%）。`APPROVED` 放行 VERIFYING；`REJECTED` 退回 CODING（最多 2 次）；fail-open。 || A cross-model CritiqueAgent scores code on four dimensions; approve advances, reject loops back up to twice.

### 阶段 7：验证 || Stage 7: Verification
`ExecutorVerifier`（`goal/verifier.py`）白名单命令 + shell 元字符检测 + 真实子进程执行（可选 Docker）。防幻觉 `validate_full`（`hallucination/pipeline.py`）按 L1→L4→L3→L2→L6→L8→L7→L5 顺序运行，L1/L7 致命失败即前向终止。`CircuitBreaker`（`gateway/circuit_breaker.py`）在 LLM 调用前后计数，连续 5 次失败或 60s 错误率>30% 熔断。 || ExecutorVerifier runs whitelisted commands; validate_full runs the layered pipeline with fatal early-stop; the circuit breaker trips on repeated failures.

### 阶段 8：检查点与回滚 || Stage 8: Checkpoint & Rollback
`CheckpointManager`（`checkpoint/manager.py`）双层冷热（Redis TTL=3600s → PG → 内存 → 磁盘），`version` 乐观锁。`resume()` 从断点续跑；`cancel_task()` 写 CANCELLED（version+1 防覆盖）。 || CheckpointManager persists across four tiers with optimistic versioning; resume continues from the breakpoint.

### 阶段 9：图谱交互 || Stage 9: Graph Interaction
`CodeGraphEngine`（`graph/engines/code_graph.py`）启动全量 `build_index`，L1 查符号存在性，Stage2 上下文加载，`GraphWatcher` 文件变更增量更新。`TaskGraph`（DAG 节点）、Goal 依赖 DAG、`MetaGraph`、Git 操作图谱在对应阶段读写。 || CodeGraphEngine builds/queries symbols with incremental updates on file changes; task/dependency/meta/git graphs are read-written at their stages.

### 阶段 10：审计与可观测 || Stage 10: Audit & Observability
`AuditLogger`（`observability/audit.py`）记录 component/operation/task_id/status；`LessonStore` SHA256 哈希链存教训（防篡改）；`EventBus`（`events/bus.py`）广播 `task:update`/`token:update` 到驾驶舱；`TraceCollector` 后台 flush span 到 `orbit_trace.db`。 || AuditLogger + tamper-proof LessonStore + EventBus broadcast + TraceCollector.

### 阶段 11：交付 || Stage 11: Delivery
Goal：子任务 DONE 后 `WorktreeManager` 清理，PR 合并门禁 = CritiqueAgent APPROVED + ExecutorVerifier 通过 + RegressionGuard 无回归；每 5 子任务做 `AlignmentCheck`，连续 3 次失败自动终止。单任务：到 DONE 推 100% 进度，`Wiring.on_task_end` 记录 + 异步 `maybe_distill` 周期蒸馏。 || Goal delivery merges via a three-condition gate with periodic alignment checks; single-task publishes completion and triggers periodic distillation.

## 4.4 全景时序图 || End-to-End Sequence

```
请求(NL/PRD) ─▶ 入口(chat/goal/tasks/loop)
                 │
                 ▼
        意图路由 Chatter ─(programming)▶ Clarifier(V1–V5) ─▶ StructuredPRD
                 │
   Goal模式 ─▶ IntakeRouter ─▶ 拆解(Spec+TaskDAG) ─▶ 用户确认
                 │
                 ▼
        调度器状态机  IDLE→PARSING→SCOPING→PLANNING→CODING→VERIFYING→DONE
                 │            每转换点存 Checkpoint（Redis→PG→内存→磁盘）
                 ▼
        Agent 执行(ReAct + Reflection/PreAct/VIGIL/MCTS)
                 │  write_file 后 validate_quick(L1+L4+L3)
                 ▼
        CritiqueGate(跨模型四维评分) ─(reject≤2)▶ 退回 CODING
                 │(approve)
                 ▼
        验证 ExecutorVerifier + validate_full(L1..L8) + CircuitBreaker
                 │
                 ▼
        图谱读写(代码/DAG/元/Git) ── 审计链 task_audit_trail + Trace + EventBus→驾驶舱
                 │
                 ▼
        交付：PR 合并门禁(Critique✓ + Verify✓ + Regression✓) / 报告 / 看板
```

---

[← 返回目录 || Back to index](README.md) · [下一章：方法论与理论 → || Next: Methodology & Theory →](05-methodology-theory.md)
</content>
