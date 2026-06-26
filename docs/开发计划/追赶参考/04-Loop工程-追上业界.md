# Loop Engineering——追上业界方案

> 参考源: Claude Code, OpenCode, Hermes, MiMo Code

---

## 一、业界最佳实践

### Claude Code：while + tool_calls（极简核心）

```typescript
// 核心只有 ~50 行
while (true) {
    const response = await callClaude(messages, tools);
    if (response.stop_reason === "end_turn") break;
    if (response.stop_reason === "tool_use") {
        for (const tc of response.tool_calls) {
            const result = await executeTool(tc);
            messages.push({role: "tool", content: result});
        }
    }
    if (turnCount++ > maxTurns) break;
}
```

**关键**：没有分类器、没有 DAG、没有 RAG pipeline——模型自己决定一切。循环就是 `call → tool_calls? → execute → loop`。

### OpenCode：runLoop() + 流式事件

```typescript
// session/prompt.ts:1400
while (true) {
    const result = await llm.stream({messages, tools});
    for (const event of result.fullStream) {
        switch (event.type) {
            case "text-delta":    appendText(event.textDelta); break;
            case "tool-call":     await handleToolCall(event); break;
            case "finish-step":   recordUsage(); break;
        }
    }
    if (isFinished) break;
    if (needCompaction) compactContext();
    if (stepCount >= maxSteps) break;
}
```

**4 个退出条件**: 正常完成 / 权限阻断 / 上下文溢出 / 步数上限

### Hermes：可中断 API 调用 + 并发工具执行

```python
# 核心循环 (ai_agent.py)
while True:
    # 1. 构建 messages（含 prompt 缓存标记）
    messages = self._build_messages()

    # 2. 可中断 API 调用（后台线程跑 HTTP）
    response = await self._interruptible_api_call(messages, tools)

    # 3. 解析响应
    if response.tool_calls:
        # 并发执行独立工具（ThreadPoolExecutor, max 8 workers）
        results = await self._execute_tools_concurrent(response.tool_calls)
        messages.extend(results)
        continue  # ← 回到步骤 1
    else:
        # 文本响应 → 持久化 → 返回
        self._persist_session()
        return response.text
```

**并发策略**:
- 独立工具调用 → `ThreadPoolExecutor(8)` 并行
- 交互式工具（如 clarify）→ 强制串行
- 路径作用域工具（read/write/patch）→ 独立路径可并行

### MiMo Code：/goal + judge 模型

```
用户: /goal "所有测试通过，覆盖率 >80%"
Agent: 写代码 → 跑测试 → 检查覆盖率 → 79% → 不够 → 继续改
       → 81% → 调 judge 模型验证 → "目标已达成" → 停止
```

**防止假完成**: 独立 judge 模型验证任务是否真正满足停止条件。

---

## 二、Orbit 当前状态

```python
# scheduler/orchestrator.py
# Agent 只 execute() 一次——没有工具调用循环
async def _agent_cycle(self, task_id, state, context):
    role = role_map[state]
    return await self._run_agent(role, task_id, context)
    # 一次调用 → 一次输出 → 结束
    # 没有: while tool_calls: execute_tool() → loop
```

**问题**：
- Agent 没有 ReAct 循环——一次 LLM 调用，一次输出
- 没有工具调用——Agent 只能"说"，不能"做"
- 没有流式处理——等全部完成才返回
- 没有 stop reason 判断——不知道 LLM 为什么停
- 失败直接 FAILED——不重试、不回退、不升级

---

## 三、实施方案

### Phase 1：ReAct 循环（对标 OpenCode·2天）

```python
# src/orbit/agents/developer.py 改造
class DeveloperAgent(BaseAgent):
    MAX_TURNS = 20

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        messages = [{"role": "system", "content": self.system_prompt()},
                    {"role": "user", "content": input_data.task}]
        tools = self._resolve_tools()  # 从 ToolRegistry 获取

        for turn in range(self.MAX_TURNS):
            # 1. 调 LLM
            response = await self.llm.generate(messages, tools)

            # 2. 判断停止原因
            if response.stop_reason == "end_turn":
                return AgentOutput(status="ok", result=self._parse_result(response))

            # 3. 执行工具调用
            if response.stop_reason == "tool_calls":
                for tc in response.tool_calls:
                    result = await self.tool_registry.dispatch(tc.name, tc.args)
                    messages.append({"role": "tool", "content": str(result)})
                continue  # ← 回到步骤 1

        raise MaxTurnsExceeded(f"超过 {self.MAX_TURNS} 轮未完成")
```

### Phase 2：流式 + 中断（对标 Hermes·1天）

```python
async def execute(self, input_data: AgentInput) -> AgentOutput:
    stream = await self.llm.generate_stream(messages, tools)

    async for event in stream:
        if isinstance(event, TextDelta):
            self._append_text(event.text)        # 实时输出到驾驶舱
        elif isinstance(event, ToolCall):
            await self._handle_tool(event)        # 执行工具
        elif isinstance(event, StepFinish):
            self._record_usage(event.usage)       # 记录 token 消耗

    return self._final_output()
```

### Phase 3：失败升级循环（对接已有 escalation.py·1天）

```python
# 接入 scheduler/escalation.py + merge_engine.py
async def run_with_escalation(self, task, agent_name):
    tier = ModelTier.TIER_1
    attempts = []

    for _ in range(MAX_ESCALATION):
        result = await self._execute_at_tier(task, agent_name, tier)
        attempts.append(result)

        if not needs_escalation(result.output, result.error):
            return result  # 成功，不升级

        tier = next_tier(tier)
        if tier is None:
            break

    # 所有 tier 都失败 → 合并
    engine = MergeEngine(self.llm)
    return await engine.merge(attempts, task)
```

### Phase 4：/goal 驱动停止（对标 MiMo·2天）

```python
class GoalChecker:
    def __init__(self, judge_llm: LLMClient):
        self.judge = judge_llm

    async def check(self, goal: str, current_state: dict) -> bool:
        """独立 judge 模型验证是否满足停止条件。"""
        prompt = f"""
        目标: {goal}
        当前状态: {current_state}
        目标是否已达成？回答 YES/NO，附理由。
        """
        resp = await self.judge.generate(prompt)
        return resp.content.strip().upper().startswith("YES")
```

---

## 四、参考源码位置

| 项目 | 关键文件 | 行数 |
|------|---------|------|
| Claude Code | `agent_loop.ts` (leaked, ~50 行核心) | ~50 |
| OpenCode | `session/prompt.ts:1400` runLoop() | ~200 |
| OpenCode | `session/processor.ts:350` Doom Loop | ~25 |
| Hermes | `ai_agent.py` _interruptible_api_call + concurrent tools | ~150 |
| MiMo Code | Fork from OpenCode + goal checker | ~100 |
