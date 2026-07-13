# 阶段1 PRD：Agent 级 Subagent 生成能力

> 日期: 2026-07-13 | 状态: 待确认

---

## 1. 背景与问题

### 1.1 现状

Orbit 已实现 ActorSpawn（[actors/spawn.py](../../../src/orbit/actors/spawn.py)）+ ComposeOrchestrator（[compose/orchestrator.py](../../../src/orbit/compose/orchestrator.py)）——编排层可在 spec 解析后按拓扑排序 spawn 子 Agent。但当前存在能力断层：

```
编排层: ComposeOrchestrator → ActorSpawn.spawn() → 多个 ReActAgent ✅
Agent层: ReActAgent 循环 → 工具: {read_file, write_file, edit_file, exec_command, grep, glob}
                          ❌ 无 spawn_subagent 工具——Agent 不能自主并行
```

**后果**：
- DeveloperAgent 调研 5 个文件 → 串行 read_file，不能并行 spawn 只读子 Agent
- ReviewerAgent 审查代码 → 不能并行 spawn 安全/性能/正确性三个维度的子 Reviewer
- QAAgent 生成测试 → 不能并行 spawn 正常/边界/异常三个子 QA
- Agent 遇到意外复杂度 → 无法动态拆分，只能硬着头皮串行

### 1.2 为什么现在做

- ActorSpawn 基础设施已完整（SQLite 状态机 + DeferredActor + Watchdog + MAX_CONCURRENT）
- 工具注册中心已支持动态注册（新 API: `register_tool()`）
- ROLE_TOOLS 权限体系已建立——新工具可精确控制授予范围
- PR#297 刚刚合并（ChatterAgent 多媒体理解）→ Agent 工具能力扩展的模式已跑通

---

## 2. 目标用户

- **DeveloperAgent**：执行编程任务时需要并行调研/实现
- **ReviewerAgent**：代码审查时需要多维并行分析
- **QAAgent**：测试生成时需要并行覆盖多种场景

**非目标用户**：ChatterAgent（对话角色）、ClarifierAgent（纯文本需求澄清）

---

## 3. 用户故事

### P0 — 核心并行能力

**故事 1**：作为 DeveloperAgent，我希望在执行任务时能 spawn 子 Agent 并行调研不同文件，以便在上下文窗口受限时仍能高效收集信息。

验收标准：
- [ ] `spawn_subagent` 工具注册到 ToolRegistry
- [ ] DeveloperAgent 可调用 `spawn_subagent(role="architect", task="分析 xxx 模块的架构")`
- [ ] 子 Agent 返回结构化结果（status + result + error）
- [ ] 父 Agent 可在 ReAct 循环中 await 子 Agent 结果

**故事 2**：作为 ReviewerAgent，我希望 spawn 3 个子 Reviewer（安全/性能/正确性维度），并行审查同一 diff，汇总结果。

验收标准：
- [ ] ReviewerAgent 可并行 spawn 多个子 Agent（≤MAX_CONCURRENT=4）
- [ ] 子 Agent 错误不影响其他子 Agent（错误隔离）
- [ ] 父 Agent 收集所有子 Agent 结果后继续 ReAct 循环

**故事 3**：作为 QAAgent，我希望 spawn 子 QA 并行生成正常路径/边界/异常测试用例。

验收标准：
- [ ] QAAgent 可 spawn 3 个子 QA，各自生成不同维度的测试
- [ ] 结果合并到父 Agent 的最终输出

### P1 — 安全与可控

**故事 4**：作为系统管理员，我希望限制 Agent 级 spawn 的并发数、深度、角色范围，防止失控。

验收标准：
- [ ] 子 Agent 不能再 spawn 孙子 Agent（max_spawn_depth=1）
- [ ] 全局 MAX_CONCURRENT 对所有 spawn（编排层+Agent 层）共享
- [ ] 子 Agent 角色限制为开发类角色（architect/developer/reviewer/qa），不能 spawn chatter/clarifier

**故事 5**：作为系统管理员，我希望每次 spawn 被记录到审计日志，可追溯"谁 spawn 了谁、为什么"。

验收标准：
- [ ] 每次 spawn 记录 parent_task_id + reason + 时间戳
- [ ] 前端（驾驶舱）可展示任务树（父→子关系）

### P2 — 体验优化

**故事 6**：作为 DeveloperAgent，子 Agent 超时时不应阻塞父 Agent——超时结果标记为失败，父 Agent 继续执行。

验收标准：
- [ ] 子 Agent 有独立超时（默认 120s）
- [ ] 超时返回 `{status: "timeout", partial_result: "..."}`，不抛异常

---

## 4. 验收标准汇总

| # | 验收标准 | 优先级 |
|---|---------|--------|
| AC1 | `spawn_subagent` 工具注册，Developer/Reviewer/QA 可调用 | P0 |
| AC2 | 子 Agent 返回结构化结果（status + result + error） | P0 |
| AC3 | 父 Agent 可并行 spawn 多个子 Agent（≤4） | P0 |
| AC4 | 子 Agent 错误隔离——不影响父 Agent 或其他子 Agent | P0 |
| AC5 | 子 Agent 不能再 spawn 孙子 Agent（depth=1） | P1 |
| AC6 | 全局 MAX_CONCURRENT 共享（编排层+Agent 层不超限） | P1 |
| AC7 | spawn 记录 parent_task_id + reason → 审计日志 | P1 |
| AC8 | 前端展示任务树（父→子） | P1 |
| AC9 | 子 Agent 超时独立处理（默认 120s，不阻塞父） | P2 |

---

## 5. 领域特定影响分析

### 5.1 调度器影响

| 维度 | 影响 |
|------|------|
| 状态转换 | Scheduler 需感知子 Agent 状态——当前 ActorRegistry 已有 parent_task_id，Scheduler 的 `_agent_cycle` 不直接管理子 Agent 生命周期。**无需改 Scheduler 状态机**——子 Agent 由 ActorSpawn 管理，父 Agent 在 ReAct 循环中 await DeferredActor |
| 检查点 | 父 Agent 的检查点**不自动覆盖**子 Agent 状态——子 Agent 独立于 ActorRegistry。如果父 Agent 回滚，已 spawn 的子 Agent 不受影响（zombie 由 Watchdog 清理） |
| 回滚路径 | 无需特殊处理——父 Agent 回滚不影响已完成的子 Agent 结果（已写入 ActorRegistry） |
| 并发 | **关键风险**——现有 MAX_CONCURRENT=4 是全局的。如果 ComposeOrchestrator 已经 spawn 了 4 个 Agent，Agent 级 spawn 会失败（返回错误，不崩溃） |

### 5.2 防幻觉层影响

| 层 | 影响 | 风险 |
|----|------|------|
| L1 静态校验 | 子 Agent 输出受 L1 校验 | 无增量影响 |
| L2 动态追踪 | 子 Agent 的工具调用链需独立追踪 | 低——当前追踪按 task_id 隔离 |
| L3 熵监控 | 子 Agent 不共享父 Agent 的熵窗口 | 中——子 Agent 可能重复父 Agent 已确认的错误 |
| L4-L8 | 子 Agent 独立过防幻觉管线 | 无增量影响 |

**缓解措施**：子 Agent 的 system prompt 注入父 Agent 的已验证上下文摘要（≤500 字符），避免子 Agent 重复犯错。

### 5.3 图谱影响

无直接 Schema 变更。子 Agent 通过工具访问图谱——与普通 Agent 行为一致。

### 5.4 工具注册中心影响

- 新增 `spawn_subagent` 工具（新 API: `register_tool()`）
- ROLE_TOOLS 新增：developer/reviewer/qa +`spawn_subagent`
- 工具 schema 包含：`role`, `task`, `context`（可选）, `timeout`（可选）

---

## 6. 边缘情况

| # | 场景 | 预期行为 |
|---|------|---------|
| E1 | Agent spawn 时全局并发已满（4/4） | 返回错误 `{status: "rejected", reason: "concurrency_limit", current: 4, max: 4}` |
| E2 | 子 Agent 执行中超时（120s） | 返回 `{status: "timeout", partial_result: "..."}`，父 Agent 继续 |
| E3 | 子 Agent 尝试 spawn 孙子 Agent | 工具返回错误 `"spawn_depth_exceeded: max depth is 1"` |
| E4 | 子 Agent 指定 chatter/clarifier 角色 | 工具返回错误 `"role_not_allowed: chatter/clarifier cannot be spawned"` |
| E5 | 父 Agent 回滚（检查点恢复）前已 spawn 子 Agent | 子 Agent 继续执行（独立生命周期），Watchdog 清理完成/超时后的子 Agent |
| E6 | 子 Agent LLM 调用失败（API 不可用） | 子 Agent 返回 `{status: "error", error: "llm_unavailable"}`，父 Agent 收到失败结果 |
| E7 | 父 Agent 在子 Agent 完成前被 cancel | 子 Agent 收到 cancel 信号（CancellationToken 传播） |
| E8 | 同一父 Agent 连续 spawn 100 个子 Agent | ToolRegistry 的 doom loop 检测介入——同参数 3 连续调用触发拦截 |

---

## 7. Non-Goals

- ❌ 不实现递归 spawn（子→孙→曾孙）——本次只允许 1 层
- ❌ 不实现 Agent 间消息传递协议——已有 `AgentMessageBus`，本次不改
- ❌ 不实现子 Agent 的检查点/回滚——子 Agent 无状态，完成后丢弃
- ❌ 不给 chatter/clarifier 开放 spawn 权限
- ❌ 不修改 ComposeOrchestrator 的 spec 解析逻辑

---

## 8. 成功指标

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| Reviewer 审查耗时 | 减少 40%+（并行 3 维度） | 对比串行 vs 并行审查时间 |
| 子 Agent 错误率 | <5%（超时+LLM 错误） | ActorRegistry 统计 |
| 并发利用率 | spawn 成功率达到 90%+（非并发满时） | ToolRegistry 审计 |

---

## 9. 待确认问题

> 以下问题需用户确认后进入阶段 2。

1. **子 Agent 角色范围**：允许 developer/architect/reviewer/qa——是否也允许 config_manager？建议暂不包括。
2. **超时时间**：默认 120s——对于复杂任务是否足够？是否需要父 Agent 可指定超时参数？
3. **子 Agent 结果大小限制**：当前 ToolEntry 输出截断 10K chars——子 Agent 结果可能超限。建议提高至 50K 或不做截断。
4. **是否需要前端可视化**：P1 AC8 "前端展示任务树"——是否本次实现？建议先做后端日志，前端可视化后续 PR。
5. **Token 预算继承**：子 Agent 是否从父 Agent 继承 token 预算，还是独立预算？建议独立（子 Agent 用 T2 模型，低成本）。

---

## 10. 基线引用

- 架构分析对话记录：[2026-07-13 对话——Orbit Subagent 系统代码 vs 文档对比]
- 当前 ActorSpawn 实现：[actors/spawn.py](../../../src/orbit/actors/spawn.py)
- 当前 ToolRegistry：[tools/registry/core.py](../../../src/orbit/tools/registry/core.py)
- ROLE_TOOLS 权限体系：[tools/registry/core.py:216-224](../../../src/orbit/tools/registry/core.py#L216)
- PR #297 模式参考：ChatterAgent 工具扩展（2026-07-13 合并）
