# 阶段1 PRD：Orbit 全链路测试库

> 版本 1.0 | 2026-06-30 | 状态：待用户确认

---

## 1. 背景与问题陈述

### 1.1 当前状态

Orbit 拥有 1,195 个测试函数（88 文件），覆盖率 ≥80%。但测试基础设施存在以下结构性缺陷：

| 问题 | 现状 | 影响 |
|------|------|------|
| **无模型工厂** | 每个测试手写 `Task(id=..., prd=...)` 内联构造 | 重复代码，字段变更时大面积改测试 |
| **无 Mock 库** | `MockLLMClient` 只在 `tests/e2e/mock_llm.py` 一份，其他地方手写 `MagicMock` | Mock 行为不一致，集成测试不可靠 |
| **无 Builder** | Task 生命周期 6 状态，无链式构建器 | 测试 setup 动辄 60-80 行，难以阅读 |
| **无场景库** | LLM 熔断/检查点恢复/沙箱超时等场景每次重写 | 常见故障模式未沉淀，新场景遗漏回归 |
| **无专用断言** | 防幻觉层/检查点/熔断状态无复用断言 | 断言逻辑散落，误报风险 |
| **4 模块零覆盖** | `files/` `loop/` `lsp/` `review/` 无任何测试 | 生产代码无安全网 |

### 1.2 用户痛点

- **开发者写新测试**：需先读懂 60 行 setup 代码，然后复制粘贴修改。耗时且易错。
- **CI 失败排查**：Mock 行为与真实组件差异大，CI 失败可能是 Mock 问题而非代码 bug。
- **回归遗漏**：LLM 熔断、沙箱超时、检查点回滚等故障场景手工重写，新功能容易破坏已有行为。
- **覆盖率冲刺**：`tests/unit/test_coverage_*.py` 10 个专用文件（169 测试）专门填补覆盖率缺口，说明工具链不足导致测试难写。

---

## 2. 目标用户与使用场景

### 2.1 目标用户

| 用户 | 使用方式 |
|------|---------|
| **Orbit 开发者**（写新模块） | 用 `factories` + `mocks` 写单元测试 |
| **Orbit 维护者**（改核心模块） | 用 `builders` + `scenarios` 验证回归 |
| **CI 系统** | 用 `scenarios` 跑标准化冒烟 |
| **新贡献者** | 读 `scenarios/` 理解系统行为 |

### 2.2 核心使用场景

1. **写新 Agent 角色**：`factories.task()` + `mocks.llm_client()` → 30 秒内可测试
2. **改调度器状态机**：`builders.task_chain()` 遍历全状态转换 → 发现回归
3. **改防幻觉层**：`scenarios.hallucination()` 覆盖 L1-L8 全部拦截场景
4. **改 LLM 网关**：`mocks.llm_client.with_failures(3).then_success()` 模拟熔断
5. **补零覆盖模块**：`factories.*` 降低写测试的门槛

---

## 3. 用户故事

### P0 — 核心（必须交付）

| ID | 用户故事 | 验收标准 |
|----|---------|---------|
| **US-1** | 作为开发者，我能用一行代码创建带完整字段的 Task 测试实例 | `factories.task(state=TaskState.CODING)` 返回有效 Task，所有必填字段已填充 |
| **US-2** | 作为开发者，我能用可配置 Mock 替代真实 LLM 调用 | `mocks.llm_client(fixed_response=..., fail_count=3)` 行为符合预期 |
| **US-3** | 作为开发者，我能用 Builder 一键走完 Task 生命周期 | `builders.task_chain().start(prd).run_to_completion()` 返回完整 AgentOutput |
| **US-4** | 作为维护者，我能运行预定义故障场景验证核心行为 | `scenarios.normal_flow` / `scenarios.circuit_breaker` / `scenarios.checkpoint_recovery` 全部通过 |
| **US-5** | 作为维护者，我能在 30 分钟内为未覆盖模块写出第一个测试 | `factories.*` + `mocks.*` + Builder 组合使用 |

### P1 — 重要（第二批交付）

| ID | 用户故事 | 验收标准 |
|----|---------|---------|
| **US-6** | 作为开发者，我能模拟 DAG 拓扑排序+分层并发执行 | `builders.dag_chain().with_nodes(5).run()` 返回分层结果 |
| **US-7** | 作为开发者，我能用 Goal 全链路 Builder | `builders.goal_chain().intake(...).clarify().decompose().execute()` |
| **US-8** | 作为开发者，我能模拟 WebSocket 对话→澄清→创建任务 | `builders.chat_chain().dialog([...]).create_task()` |
| **US-9** | 作为 CI，每个故障场景有独立标记可选择性运行 | `pytest -m "scenario_circuit_breaker"` 只跑熔断场景 |
| **US-10** | 作为开发者，我能用防幻觉专用断言验证 L1-L8 层 | `assert_layer_passed(result, "L1")` / `assert_layer_blocked(result, "L3")` |

### P2 — 锦上添花（第三批交付）

| ID | 用户故事 | 验收标准 |
|----|---------|---------|
| **US-11** | 作为新贡献者，场景文档自动生成可读的行为描述 | 每个 Scenario 有 `__doc__` 描述用户视角的操作 |
| **US-12** | 作为开发者，Mock 支持录制-回放模式 | `mocks.llm_client.record("fixture.json")` / `.replay("fixture.json")` |
| **US-13** | 作为 CI，测试库自身有 100% 覆盖率 | `tests/lib/` 自身测试覆盖所有工厂/Mock/Builder |
| **US-14** | 作为开发者，测试数据生成器支持中文业务场景 | `generators.prd_chinese()` 生成中文 PRD 文本 |

---

## 4. 功能需求

### 4.1 模块范围

```
tests/lib/
├── factories/        # 模型工厂 — 一行创建有效实例
├── mocks/            # 可配置 Mock — 注入失败/延迟/特定输出
├── builders/         # 业务流构建器 — 链式构建完整链路
├── scenarios/        # 预定义场景 — 真实用户操作序列
└── assertions/       # Orbit 专用断言
```

### 4.2 各子模块详细需求

#### 4.2.1 factories/ — 模型工厂

每个工厂必须：
- 所有必填字段有合理默认值（`id` 用 UUID，`created_at` 用 `datetime.now(UTC)`）
- 支持 `**kwargs` 覆盖任意字段
- 返回完整有效的 Pydantic 模型或 dataclass 实例

| 工厂 | 产出类型 | 关键默认值 |
|------|---------|-----------|
| `factories.task()` | `Task` | state=IDLE, prd="测试需求：实现用户登录", priority=5 |
| `factories.agent_input()` | `AgentInput` | role=DEVELOPER, task=默认Task, context=L1-L5 空 |
| `factories.agent_output()` | `AgentOutput` | status="ok", turns=3, tool_calls=2 |
| `factories.llm_request()` | `LLMRequest` | model="deepseek-v4-pro", messages=[system+user], temperature=0.7 |
| `factories.llm_response()` | `LLMResponse` | content="...", usage={prompt:100,completion:200}, model=... |
| `factories.checkpoint()` | `Checkpoint` | task_id=..., state=CODING, retry_count=0, version=1 |
| `factories.graph_node()` | `GraphNode` | id=UUID, agent_role=DEVELOPER, status=PENDING |
| `factories.stream_event()` | `StreamEvent` | TEXT_DELTA/TOOL_CALL/FINISH_STEP |
| `factories.sandbox_result()` | `SandboxResult` | exit_code=0, stdout="OK", duration_ms=150 |
| `factories.audit_entry()` | `AuditEntry` | trace_id=UUID, event="task.state_change" |
| `factories.prd()` | `str` (结构化 PRD) | 目标、范围、验收标准、约束的完整文本 |

#### 4.2.2 mocks/ — 可配置 Mock

每个 Mock 必须：
- 100% 兼容被替代组件的接口（类型签名一致）
- 支持链式配置（`.with_*.then_*` 风格）
- `call_count` / `calls` 属性追踪调用历史
- 支持 `reset()` 重置状态

| Mock | 替代组件 | 关键配置 |
|------|---------|---------|
| `MockLLMClient` | `gateway/client.py:LLMClient` | `fixed_response`, `fail_count`, `stream_chunks`, `tool_calls`, `latency_ms` |
| `MockSandbox` | `sandbox/executor.py:Sandbox` | `exit_code`, `stdout`, `stderr`, `timeout_seconds`, `oom` |
| `MockCheckpointManager` | `checkpoint/manager.py:CheckpointManager` | `redis_available`, `pg_available`, `version_conflict_on_save` |
| `MockCircuitBreaker` | `gateway/circuit_breaker.py:CircuitBreaker` | `state` (CLOSED/OPEN/HALF_OPEN), `failure_count`, `error_rate` |
| `MockKnowledgeStore` | `knowledge/store.py:KnowledgeStore` | `query_results`, `hit/miss`, `latency_ms` |
| `MockEventBus` | `events/bus.py:EventBus` | `queue_full`, `subscriber_count` |
| `MockToolRegistry` | `tools/registry.py:ToolRegistry` | `tool_results`, `rate_limited`, `doom_loop_detect` |

#### 4.2.3 builders/ — 业务流构建器

每个 Builder 必须：
- 链式 API（`.step1().step2().done()` 风格）
- 内置默认值（一行调用走通全链路）
- 每步可覆盖（注入自定义 Mock）
- `assert_*()` 方法做结果校验

| Builder | 构建链路 | 关键方法 |
|---------|---------|---------|
| `TaskChain` | IDLE→PARSING→PLANNING→CODING→VERIFYING→DONE | `.start(prd)`, `.with_llm()`, `.with_sandbox()`, `.run_to_completion()`, `.assert_done()` |
| `DagChain` | TaskGraph→拓扑排序→分层并发→结果 | `.with_nodes(n)`, `.with_dependencies(edges)`, `.run()`, `.assert_node_order()` |
| `GoalChain` | intake→clarify→decompose→execute→critique→merge | `.intake(goal)`, `.clarify()`, `.decompose()`, `.execute()`, `.assert_merged()` |
| `ChatChain` | WebSocket dialogs→ClarifierAgent→task create | `.dialog(messages)`, `.create_task()`, `.assert_task_created()` |

#### 4.2.4 scenarios/ — 预定义场景

每个 Scenario 必须是独立可运行的 pytest 测试函数，带 `@pytest.mark.scenario_*` 标记。

| 场景 | 覆盖内容 | 标记 |
|------|---------|------|
| `normal_flow.py` | 正常需求→自动实现→验证通过 | `scenario_normal` |
| `circuit_breaker.py` | LLM 5 次连续失败→熔断 OPEN→半开→恢复 | `scenario_circuit_breaker` |
| `checkpoint_recovery.py` | 编码阶段崩溃→从检查点恢复继续 | `scenario_checkpoint` |
| `hallucination.py` | L1-L8 各层拦截一例 | `scenario_hallucination` |
| `sandbox_isolation.py` | 沙箱超时/权限拒绝/网络隔离 | `scenario_sandbox` |
| `concurrent.py` | 3 任务并行→DAG 分层→资源竞争 | `scenario_concurrent` |
| `edge_cases.py` | 空PRD/超长代码/无效工具/doom-loop | `scenario_edge` |

#### 4.2.5 assertions/ — 专用断言

| 断言 | 用途 |
|------|------|
| `assert_state_transition(result, from_, to)` | 验证状态机转换 |
| `assert_checkpoint_saved(checkpoint, expected_state)` | 验证检查点已保存且内容一致 |
| `assert_hallucination_layer_passed(result, layer)` | 验证防幻觉层通过 |
| `assert_hallucination_layer_blocked(result, layer, reason)` | 验证防幻觉层拦截 |
| `assert_circuit_state(breaker, expected_state)` | 验证熔断器状态 |
| `assert_fallback_triggered(result, from_model, to_model)` | 验证降级触发 |
| `assert_sandbox_isolated(result)` | 验证沙箱隔离执行 |
| `assert_dag_topological_order(execution_log)` | 验证 DAG 拓扑序 |

---

## 5. 领域特定影响分析

### 5.1 调度器影响

- **无新增/修改状态**：测试库不改变调度器状态机，只提供测试辅助
- **检查点**：`MockCheckpointManager` 需模拟 Redis/PG 断连、版本冲突等故障模式
- **回滚**：`builders.task_chain()` 需覆盖"崩溃后从检查点恢复"路径
- **并发**：`scenarios/concurrent.py` 需验证并行任务不相互干扰

### 5.2 防幻觉层影响

- **无修改**：测试库不改变 L1-L8 判定逻辑
- **覆盖要求**：`scenarios/hallucination.py` 每层至少 1 个拦截用例和 1 个通过用例
- **误报/漏报**：Mock 行为需与真实 LLM 输出一致，避免测试通过但生产失败

### 5.3 图谱影响

- **无 Schema 变更**：测试库不修改 CodeGraph SQLite 结构
- **隔离**：测试库自身应在 `:memory:` SQLite 中运行，不与真实图谱数据混合

### 5.4 沙箱影响

- **安全约束不变**：测试 Mock 不能绕过 Docker 隔离
- `MockSandbox` 只用于单元测试；集成/E2E 测试必须用真实沙箱

---

## 6. 边缘情况

| 类别 | 场景 | 预期行为 |
|------|------|---------|
| **LLM** | 连续 5 次返回 500 | CircuitBreaker → OPEN；`builders.task_chain()` 抛出 `CircuitOpenError` |
| **LLM** | 返回空 content | Agent 重试 1 次；仍空→`AgentOutput(status="error")` |
| **LLM** | 返回包含无效 tool_call 名称 | `ToolRegistry.dispatch()` 返回 error event；不崩溃 |
| **沙箱** | 代码无限循环 | 超时 SIGKILL；`SandboxTimeoutError` |
| **沙箱** | 代码尝试 `os.system("rm -rf /")` | 沙箱拒绝（网络隔离+只读挂载）；`SandboxExecutionError` |
| **检查点** | Redis 断连 | 自动降级到 PG；`CheckpointManager` 透明切换 |
| **检查点** | PG 版本冲突（并发保存） | 乐观锁重试 1 次；仍冲突→`CheckpointConflictError` |
| **DAG** | 上游节点失败 | `fail_fast`：同层下游跳过；`continue_on_error`：下游仍执行 |
| **并发** | 多 Agent 同时写同一文件 | Worktree 隔离（各自独立分支） |
| **工具** | 连续 3 次相同 tool_call | Doom-loop 检测→中断当前 turn |
| **输入** | PRD 为空字符串 | IntakeRouter 返回 `needs_clarify=True`；不崩溃 |
| **输入** | PRD 为 10 万字符超长文本 | Compressor trim 到预算内；不丢弃关键信息 |
| **内存** | MemoryStore 查询无结果 | 返回空列表；不影响主流程 |
| **知识库** | 知识库查询超时 | 降级：跳过知识增强，只基于 PRD 执行 |

---

## 7. 验收标准（AC）

### 7.1 功能 AC

| # | 验收标准 | 验证方式 |
|---|---------|---------|
| AC-1 | 所有 `factories/` 产出的实例字段完整、类型正确 | `pytest tests/lib/test_factories.py` |
| AC-2 | 所有 `mocks/` 100% 兼容被替代组件的公共接口 | `isinstance(mock, OriginalClass)` 或 Protocol check |
| AC-3 | `builders.task_chain().start(prd).run_to_completion()` 返回 `AgentOutput(status="ok")` | 集成测试 |
| AC-4 | `builders.dag_chain().with_nodes(5).run()` 返回 5 个结果，拓扑序正确 | 集成测试 |
| AC-5 | 7 个预定义场景全部通过 | `pytest tests/lib/scenarios/ -v` |
| AC-6 | 用新 lib 写测试的 setup 行数减少 50%+ | 对比改造前后的测试文件 |
| AC-7 | `files/` `loop/` `lsp/` `review/` 四个模块覆盖率 > 0% | `pytest --cov --cov-report=term` |

### 7.2 非功能 AC

| # | 验收标准 | 验证方式 |
|---|---------|---------|
| AC-8 | 测试库自身不引入新依赖（只用 pytest + stdlib） | `grep -r "import" tests/lib/` |
| AC-9 | 测试库代码量 < 3000 行（不含自身测试） | `find tests/lib/ -name "*.py" | xargs wc -l` |
| AC-10 | 现有 1,195 测试全部通过（不破坏已有测试） | `pytest tests/unit/ tests/integration/ -q` |
| AC-11 | 不影响 CI 时长（测试库自身 < 5s） | `time pytest tests/lib/` |
| AC-12 | 覆盖率 ≥80% 维持不变 | CI 门禁 |

---

## 8. Non-Goals

| 项 | 理由 |
|----|------|
| 不生成性能基准数据 | `tests/perf/` 已有，不重复 |
| 不替换现有 1,195 测试 | 增量补充，不重写历史测试 |
| 不引入 FactoryBoy / Faker 等第三方依赖 | 项目约束 #8：新依赖必须先问 |
| 不创建 HTTP 录制回放（VCR 模式） | P2 US-12 简化为文件-based 录制 |
| 不修改生产代码 | 测试库纯测试侧，零生产影响 |
| 不覆盖前端 Vue3 组件测试 | 前端测试属独立需求，本次仅后端 |

---

## 9. 版本与阶段规划

| 阶段 | 内容 | 文件数 | 预估行数 | 对应 US |
|------|------|--------|---------|---------|
| **Phase 1** | `mocks/` 全部 + `factories/` 核心 | 13 | ~1,200 | US-2, US-4(部分) |
| **Phase 2** | `factories/` 剩余 + `builders/task_chain.py` | 8 | ~800 | US-1, US-3, US-5 |
| **Phase 3** | `builders/` 剩余 + `scenarios/` + `assertions/` | 13 | ~1,000 | US-4, US-6-US-10 |
| **Phase 4** | 补 `files/` `loop/` `lsp/` `review/` 测试 | 4+ | ~600 | US-5, AC-7 |
| **Phase 5** | P2 功能 + 测试库自身测试 | 5 | ~500 | US-11-US-14 |

---

## 10. 待确认问题

| # | 问题 | 建议 | 需要用户决策 |
|---|------|------|------------|
| Q1 | Mock 应该替代原对象（monkeypatch）还是作为 fixture 注入？ | 建议 fixture 注入（不影响全局状态） | |
| Q2 | `tests/lib/` 放在 `tests/` 下还是独立包？ | 建议 `tests/lib/`（pytest 自动发现，无需改 `pyproject.toml`） | |
| Q3 | Phase 1 是否包含自身测试？ | 建议 Phase 5 统一补（先有功能再补测试） | |
| Q4 | `MockLLMClient` 已有 `tests/e2e/mock_llm.py`，是否迁移增强？ | 建议迁移到 `tests/lib/mocks/llm_client.py`，旧位置保留 import 重定向 | |
| Q5 | 是否先做 Phase 0——利用现有源码再做一次 gap analysis？ | 可做，但 PRD 已经够详细。建议直接进入 Phase 1 | |

---

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Mock 行为与真实组件不一致，测试假阳性 | 中 | 高——CI 通过但生产失败 | Mock 接口与真实组件同步更新；关键路径保留 E2E 测试 |
| 测试库过度设计，实际使用率低 | 低 | 中——浪费开发时间 | 按 Phase 分阶段交付，每阶段收集反馈后再做下一阶段 |
| 与现有 1,195 测试的 fixture 命名冲突 | 低 | 中——CI 失败 | 所有 fixture 加 `lib_` 前缀；conftest 只声明不自动激活 |

---

> **阶段门禁**：本文档完稿，请用户逐条审查。确认后进入阶段 2（技术方案）。
>
> 重点确认：Q1-Q5 的决策、Phase 1-5 的范围划分、验收标准 AC-1 到 AC-12 是否完整。
