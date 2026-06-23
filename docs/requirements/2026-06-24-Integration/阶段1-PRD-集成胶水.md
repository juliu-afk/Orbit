# PRD+ADR：Agent 集成胶水

## Step I1：Orchestrator-Agent 全链路集成

| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 各模块独立可用——AgentFactory 能创建 5 种 Agent、MessageBus 能通信、ToolRegistry 能注册工具、Orchestrator 有 DAG 状态机——但 Orchestrator 的 `_run_agent()` 是占位代码，没有真正调用 AgentFactory → Agent.run(context) → 通过 MessageBus 协作 → 调用 ToolRegistry 的完整链路。需要集成胶水把模块串起来。 |
| **用户故事** | 作为用户，我通过 REST API 提交一个任务 → 调度器按 DAG 状态机推进 → 在 CODING 状态时拉起 DeveloperAgent 协程 → Agent 通过 MessageBus 请求 ReviewerAgent → Agent 通过 ToolRegistry 调用知识查询工具 → 结果写入检查点 → 最终返回任务完成。整个过程自动化。 |
| **需求描述** | ① `_run_agent()` 实现：AgentFactory 创建实例 → `_build_context()` 构建 L1-L5 → `await agent.run(context)` → 结果写入 Checkpoint。② Agent 超时处理：`asyncio.wait_for(agent.run(), timeout=300)`。③ Agent→Agent 通信：Agent 通过注入的 MessageBus 实例调用其他 Agent。④ Agent→工具调用：Agent 通过注入的 ToolRegistry 调用知识查询等工具。⑤ 全链路可观测：每一步通过 AgentOps AuditLogger 记录。 |
| **范围 (Do/Don't)** | **Do：**Orchestrator._run_agent() 真实实现、Agent 依赖注入 (LLMClient/MessageBus/ToolRegistry/Checkpoint)、TaskContext 构建、超时/错误处理。<br>**Don't：**不修改已有模块接口；不实现新的 Agent 角色；不处理 LLM 调用实际逻辑（那是 Prompt 工程的职责）。 |
| **数据契约** | `Orchestrator._run_agent(role, task) → AgentResult`<br>`Orchestrator._build_context(task) → TaskContext (L1-L5)` |
| **异常定义** | `AgentTimeoutError`：5 分钟超时 → 取消协程，任务标记 FAILED。<br>`AgentBuildError`：Factory 无法创建 Agent → 记录错误，降级为 L2 规则引擎。 |
| **成功标准→验收** | **SC1:** 全链路通 → **AC1:** `POST /api/v1/tasks` 创建任务 → Orchestrator 推进到 DONE → 检查点有结果。<br>**SC2:** Agent 协作 → **AC2:** DeveloperAgent 通过 MessageBus 成功请求 ReviewerAgent 并获响应。<br>**SC3:** 工具调用 → **AC3:** Agent 通过 ToolRegistry 成功调用知识查询工具。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈** | Python asyncio；复用已有 AgentFactory/MessageBus/ToolRegistry/CheckpointManager/AuditLogger。零新依赖。 |
| **决策** | Agent 通过**依赖注入**获取外部能力（LLMClient/MessageBus/ToolRegistry/CheckpointManager），而非全局单例。Orchestrator 在 `_run_agent()` 中将依赖注入给 Agent 实例。 |
| **理由** | ① 可测试：每个 Agent 可注入 Mock 依赖。② 解耦：Agent 不依赖全局状态。③ 与 V14.1 ADR 一致。 |
| **架构位置** | `scheduler/orchestrator.py`（`_run_agent()` + `_build_context()` 真实实现） |
| **实施细节** | **_run_agent() 流程：** 1) `AgentFactory.create(role)` 创建实例 2) `_build_context(task)` 构建 L1-L5 3) 注入依赖到 agent 实例 4) `asyncio.wait_for(agent.run(context), 300)` 5) 结果写 Checkpoint 6) 记录审计事件。**_build_context() 流程：** L1=章程规则、L2=图谱查询结果(占位)、L3=任务状态字典、L4=空字典(Agent 私有)、L5=教训库查询。 |
| **风险** | Agent.run() 内可能阻塞事件循环。缓解：Agent 基类强制 async def run()。 |
| **依赖链** | 依赖 #5 (AgentFactory)、#33 (MessageBus+ToolRegistry)、#25 (AuditLogger)、#28 (Checkpoint)。 |

---

## 测试策略

| 层 | 用例 | 覆盖 |
|----|------|------|
| 单元 | 5 | _build_context L1-L5 完整性、_run_agent 超时、Agent 依赖注入验证、MessageBus 注册、ToolRegistry 调用 |
| 集成 | 3 | 全链路 (task→DONE)、Agent 协作 (Dev→Reviewer)、工具调用 (知识查询) |
| **合计** | **8** | |
