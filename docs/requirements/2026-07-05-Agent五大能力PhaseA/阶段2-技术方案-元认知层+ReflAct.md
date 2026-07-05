# 阶段2 技术方案：Orbit 闭环容错强化——元认知层 + ReflAct 反思循环

> 生成日期：2026-07-05 | 分支：feat/agent-five-capabilities-phase-a
> 基于阶段1 PRD：阶段1-PRD-元认知层+ReflAct.md（验收标准 5 条，本次方案覆盖 5 条，无偏离）

---

## 1. 需求回顾（PRD 核心验收标准）

| # | 验收标准 | 方案对应 |
|---|---------|---------|
| AC1 | Monitor 在目标偏离时，3 个 Action 内触发告警/HITL。误报率 < 10% | §3.1 元认知层——触发器系统 + 混合检测 |
| AC2 | ReflAct Reflection 阶段每次 Observation 后自动执行。偏离检测准确率 > 80% | §3.2 ReflAct——Prompt 注入 + 结构化反思 |
| AC3 | 重复动作 5 周期内检测。误报率 < 5% | §3.1.2 重复检测器 |
| AC4 | 关键决策节点 100% 触发人工移交 | §3.1.3 HITL 集成 |
| AC5 | AgentErrorTaxonomy 分类准确率 > 75% | §3.1.4 错误分类器 |

## 2. 代码探索发现

### 关键现状（来自 src/ 源码探索）

| 发现 | 文件:行号 | 影响 |
|------|----------|------|
| ReAct 循环在 Agent 内部，不在 Scheduler | `agents/react_agent.py:236-527` | ReflAct 注入点在 Agent 层，非 Scheduler 层 |
| GoalJudge 已存在于 ReAct 循环末尾 | `react_agent.py:453-490` | **ReflAct 的精确插入点**——在 GoalJudge 之前插入 Reflection |
| 防幻觉验证器存在但**未接入执行管道** | `hallucination/` 全模块 | 独立模块，无调用方。元认知层可复用其 ValidationResult |
| HITL 基本不存在 | `meta_orchestrator.py:411-413` 自动确认 | 需要从零建 HITL 机制 |
| 已有 Doom Loop 检测（重复工具调用） | `react_agent.py:353-373` | 元认知层可复用此逻辑，扩展为通用重复动作检测 |
| 已有 IterationBudget（迭代预算） | `react_agent.py:43-60,430` | 元认知层可读此值判断资源是否接近耗尽 |
| Stream 事件模型已有 8 种类型 | `stream/events.py:1-48` | 可扩展 REFLECTION 和 METACOG_ALERT |

### 影响范围

#### 新增模块

| 文件 | 职责 |
|------|------|
| `src/orbit/metacognition/__init__.py` | 模块入口 |
| `src/orbit/metacognition/monitor.py` | Monitor Agent——独立 asyncio Task，消费 StreamEvent，运行触发器 |
| `src/orbit/metacognition/triggers.py` | 触发器系统——目标漂移（复用 GoalJudge）/ 重复动作（复用 doom_loop 逻辑）/ 延迟看门狗 |
| `src/orbit/metacognition/classifier.py` | AgentErrorTaxonomy 错误分类器 |
| `src/orbit/metacognition/hitl.py` | HITL 移交管理器——从零构建（当前 `_present_for_confirmation()` 总是返回 True） |
| `src/orbit/agents/reflection.py` | ReflAct Reflection 阶段——注入 ReActAgent 循环的 Prompt 构建 + 结构化解码 |

#### 修改模块

| 文件 | 改动 | 原因 |
|------|------|------|
| `src/orbit/agents/react_agent.py:449-493` | 在 GoalJudge 之前插入 Reflection 阶段 | **精确插入点**——LLM 输出后、GoalJudge 前 |
| `src/orbit/agents/react_agent.py:391-402` | TOOL_RESULT 后 emit 结构化事件 + 可选快速 Reflection | Monitor 数据源 |
| `src/orbit/stream/events.py` | 新增 REFLECTION / METACOG_ALERT / HITL_REQUEST 事件 | 流式事件扩展 |
| `src/orbit/ws/handler.py` | 新增 HITL 通知 WebSocket 消息类型 | HITL 前端集成 |
| `frontend/src/stores/agent.ts` | 新增 metacog_alerts / hitl_requests 状态 | 驾驶舱 UI |
| `frontend/src/components/agent/HITLModal.vue` | HITL 人工干预弹窗——选项：继续/回滚/终止/接管 | 驾驶舱 UI |

## 3. 详细设计

### 3.1 元认知层 (Monitor Agent)

#### 3.1.0 设计决策

基于 PRD 待确认问题的技术判断：

| 决策 | 选择 | 理由 |
|------|------|------|
| Monitor 实现方案 | **混合模式**：规则触发器做第一道（便宜、快速、无幻觉），可选 LLM 验证做复杂判断（目标漂移的语义判断） | 纯规则覆盖不了"目标语义漂移"；纯 LLM 太贵且有幻觉风险 |
| 与 goal/ 的关系 | **独立于 goal/，但调用 goal/ 的验证结果** | Monitor 不替代 goal verification，它监控的是 Agent 行为质量。但 Reflection 阶段会调用 goal/ 的验证方法 |
| ReflAct 深度 | **轻量级 Prompt 注入**：不创建新 Agent 实例，在主 Agent 的 ReAct 循环中插入结构化反思 Prompt | 性能开销可控（每个循环 +1 次 LLM 调用），不增加架构复杂度 |
| HITL 渠道 | **WebSocket 优先**，接口可扩展 | 驾驶舱已有 WebSocket 通道，不引入新依赖 |

#### 3.1.1 架构

```
主 Agent（执行任务）
   │
   │ ReAct 循环：Thought → Action → Observation → [Reflection ← 新增] → Thought → ...
   │
   │ 每个 Action 前后 emit 事件到 EventBus
   ▼
EventBus ────▶ Monitor Agent（独立线程/协程）
                  │
                  ├── TriggerEngine
                  │   ├── GoalDriftDetector（目标漂移检测）
                  │   ├── RepetitionDetector（重复动作检测）
                  │   └── LatencyWatchdog（延迟看门狗）
                  │
                  ├── ErrorClassifier（AgentErrorTaxonomy）
                  │
                  └── HITLManager
                      ├── 构建移交上下文（当前状态+历史+检测到的风险）
                      ├── WebSocket 通知前端
                      └── 等待人工响应或自动熔断
```

#### 3.1.2 触发器系统

三种触发器（优先级从高到低）：

**A. 重复动作检测器 (RepetitionDetector)**

```python
# 伪代码
class RepetitionDetector:
    window_size: int = 5        # 观察窗口（Action 数）
    similarity_threshold: float = 0.9  # 相似度阈值（工具+参数）
    
    def check(self, recent_actions: list[Action]) -> Alert | None:
        if len(recent_actions) < window_size:
            return None
        # 取最近 N 个 Action，计算工具名+参数的相似度
        similarity = self._compute_similarity(recent_actions[-window_size:])
        if similarity > similarity_threshold:
            return Alert(
                type=AlertType.REPETITION,
                severity=Severity.WARNING,
                message=f"检测到重复动作：最近 {window_size} 步高度相似 ({similarity:.0%})"
            )
```

**B. 目标漂移检测器 (GoalDriftDetector)**

```python
class GoalDriftDetector:
    drift_window: int = 3        # 连续漂移多少次触发告警
    
    def check(self, original_goal: str, current_action: Action, 
              reflection: Reflection | None) -> Alert | None:
        # 步骤1：规则检查——快速判断
        #    · Action 的工具类别是否与目标相关的工具类别匹配？
        #    · 时间窗口内 Action 的语义方向是否偏离目标？
        # 步骤2（可选）：LLM 二次判断——规则不确定时
        #    · 将 original_goal + recent_actions + reflection 发给 LLM
        #    · Prompt："这个 Agent 正在执行 [goal]。最近的动作是 [actions]。
        #             这些动作是否仍在推进目标？回答 YES/NO + 一句话理由"
        # 步骤3：连续 drift 计数 >= drift_window → 触发告警
```

**C. 延迟看门狗 (LatencyWatchdog)**

```python
class LatencyWatchdog:
    max_action_duration_ms: int = 300_000   # 单 Action 最长 5 分钟
    max_total_duration_ms: int = 3_600_000  # 总任务最长 1 小时
    
    def check(self, action_start_time: float, 
              task_start_time: float) -> Alert | None:
        # 检查单步超时 + 总任务超时
```

#### 3.1.3 HITL 集成

```
Monitor 触发告警
      │
      ▼
判断告警级别：
  WARNING → 记录到 EventBus，不打断主 Agent
  CRITICAL → 暂停主 Agent（PAUSE 状态），发送 HITL 请求
      │
      ▼
HITLManager.build_context(agent_state)
  → 生成移交上下文：
    {
      "alert_type": "goal_drift",
      "original_goal": "检查2024年度应收账款坏账准备计提是否充分",
      "current_action": "正在查询2023年度应付账款明细",
      "last_3_actions": [...],
      "drift_detected_at_step": 7,
      "suggested_action": "建议人工确认：当前操作是否仍在审计范围内？"
    }
      │
      ▼
WebSocket → 前端 HITLModal
  选项：[继续执行] [回滚到步骤 X] [终止任务] [人工接管]
      │
      ▼
响应 → HITLManager → 主 Agent RESUME / ROLLBACK / ABORT
```

#### 3.1.4 错误分类器 (AgentErrorTaxonomy)

```python
class AgentErrorCategory(Enum):
    GOAL_FORGETTING = "goal_forgetting"       # 目标遗忘——Agent 忘记原始任务
    CONTEXT_CONFUSION = "context_confusion"   # 上下文混淆——历史步骤混为一谈
    TOOL_MISUSE = "tool_misuse"               # 工具误用——调错工具或参数
    REFLECTION_FAILURE = "reflection_failure" # 反思失误——误判任务完成状态
    PLANNING_DEVIATION = "planning_deviation" # 规划偏差——分解出现混乱
    RESOURCE_EXHAUSTION = "resource_exhaustion" # 资源耗尽——Token/时间超限

class ErrorClassifier:
    def classify(self, alert: Alert, agent_state: AgentState) -> AgentErrorCategory:
        # 规则匹配 + LLM 兜底
```

### 3.2 ReflAct 反思循环

#### 3.2.1 精确插入点

代码探索确认：ReAct 循环在 `agents/react_agent.py:236-527`。GoalJudge 已存在于 `react_agent.py:453-490`。

```
现有流程（react_agent.py）：
  for turn in range(MAX_TURNS):          # line 236
      LLM generate_stream_with_tools()    # line 314
      for each TOOL_CALL:
          dispatch tool                   # line 378-383
          yield TOOL_RESULT               # line 391
      GoalJudge self-check               # line 453-490  ← 插入点！
          if verdict.not_ok:
              inject synthetic user turn  # 强制继续
              continue
      if no tool_calls: finish           # line 493-527

ReflAct 修改后：
  for turn in range(MAX_TURNS):
      LLM generate_stream_with_tools()
      for each TOOL_CALL:
          dispatch tool
          yield TOOL_RESULT
      [REFLECTION ← NEW]                 # 在 GoalJudge 之前
          · 结构化反思 Prompt
          · LLM 调用（轻量，非流式）
          · 解析 JSON → ReflectionResult
          · yield REFLECTION event
          · 注入反思结论到 messages[]
      GoalJudge self-check               # 保持不动
      if no tool_calls: finish
```

#### 3.2.2 执行流程

```
原有 ReAct：Thought → Action → Observation → Thought → Action → ...
ReflAct：   Thought → Action → Observation → [Reflection] → Thought → ...

Reflection 阶段做的事：
  1. 获取当前状态：我执行了什么 Action？Observation 是什么？
  2. 对比目标：我的原始目标是什么？这一步是否推进了目标？
  3. 生成反思：YES（推进了）→ 继续
              NO（没推进/偏离了）→ 下一步应该怎么做？
  4. 输出结构化反思结果 → 注入下一个 Thought 的上下文
```

#### 3.2.2 Prompt 设计

```python
REFLECTION_PROMPT = """
## Reflection Phase

You have just completed an Action and received an Observation.

### Original Goal
{original_goal}

### Current Step
- Thought (before action): {last_thought}
- Action: {last_action}
- Observation: {last_observation}

### Reflection Questions (answer each):
1. **Goal Alignment**: Does this Observation bring me closer to the Original Goal? (YES/NO/PARTIALLY)
2. **Progress Assessment**: What new information do I now have that I didn't before this step?
3. **Next Direction**: Based on the Observation, what should the next Action be? If NO to Q1, what correction is needed?
4. **Confidence**: How confident am I that I am on the right track? (0-100)

Respond in JSON:
{
  "goal_alignment": "YES|NO|PARTIALLY",
  "new_information": "...",
  "next_direction": "...",
  "confidence": 85,
  "should_continue": true,
  "correction_needed": null
}
"""
```

#### 3.2.3 与现有 goal/ 模块的协作

- `goal/verification.py` 提供 `verify_goal_alignment(goal, current_state)` ——这是结果验证（任务完成后）
- ReflAct 的 Reflection 是**过程验证**（每一步之后）
- Reflection 结果同时写入 EventBus——Monitor 可用作漂移检测的输入
- Reflection 的 `correction_needed` 不为空时 → 下一步 Action = correction，而非原计划的下一步

### 3.3 Monitor 架构（基于实际代码结构）

Monitor Agent 不是独立 LLM Agent——是**规则引擎 + 可选 LLM 验证**的轻量组件。它作为独立 asyncio Task 运行，消费 StreamEvent。

```
ReActAgent.execute_stream() (react_agent.py:236-527)
   │
   │  每个事件 yield 后 → 写入 Monitor 的 asyncio.Queue
   │
   ▼
Monitor Agent (独立 asyncio Task，metacognition/monitor.py)
   │
   │  从 Queue 消费事件
   │  运行 TriggerEngine:
   │    · RepetitionDetector (复用 doom_loop 逻辑, react_agent.py:353-373)
   │    · GoalDriftDetector (LLM 辅助)
   │    · LatencyWatchdog
   │
   │  → 无告警: 继续消费
   │  → WARNING: emit METACOG_ALERT 到 EventBus
   │  → CRITICAL: 设置 asyncio.Event → HITLManager
   │
   ▼
HITLManager (metacognition/hitl.py)
   │
   │  构建移交上下文 + WebSocket 通知前端
   │  等待响应（超时=自动熔断）
   │
   ▼
前端 HITLModal.vue → 用户选择 → WebSocket 回传 → 主 Agent 恢复/回滚/终止
```

### 3.4 状态机变更

Monitor 不修改 TaskRunner 现有的 `STATE_TRANSITIONS`（`task_runner.py:611-617`）。它通过 asyncio.Event 与主 Agent 通信：

```
```
// Monitor 不修改 TaskRunner 现有状态机。通过 asyncio.Event 通信：

主 Agent 正常执行中 (agent.execute() / execute_stream())
      │
      │  Monitor 检测到 CRITICAL ──▶ _hilt_event.set()
      │
      ▼
主 Agent (react_agent.py execute_stream 循环):
      │  每个 turn 开头检查: if self._hitl_event.is_set():
      │      await self._handle_hitl()  // 暂停，等待人工
      │      或
      │      if timeout: 自动熔断 → ABORT
      │
      ▼
_handle_hitl():
      ├── CONTINUE → 清除 event，继续循环
      ├── ROLLBACK → save_checkpoint + 回滚
      ├── STEP_BACK → 注入 Reflection prompt，要求重新规划
      └── ABORT → raise TaskAborted(纳入现有 AgentOutput.error)
```
```

## 4. 额外发现：防幻觉验证器未接入管道

代码探索发现：`hallucination/` 目录下的 L1-L9 验证器**全部未接入 Agent 执行管道**。它们作为独立模块存在，无任何调用方。`base.py:107` 的 system prompt 声称"output must pass L1-L8 validation"——但实际没有验证调用发生。

**这不是本期范围**，但元认知层的 `ValidationResult` 和 `HallucinationLevel` Schema 可以直接复用——将来接入时省去 Schema 设计。

## 5. 风险点

| 风险 | 严重程度 | 缓解 |
|------|---------|------|
| Monitor 误报导致频繁打断主 Agent | 中 | 可调节灵敏度 + WARNING/CRITICAL 分级——WARNING 不打断 |
| Reflection 增加 LLM 调用次数（~25% Token 增量） | 低 | 轻量 Prompt + 可配置跳过非关键步骤的 Reflection |
| Monitor 自身崩溃导致监控真空 | 中 | Monitor 崩溃 → 主 Agent 退化到当前状态（不加 Monitor 的基线），不会更差。主 Agent 定期 ping Monitor——如果无响应则降级运行 |
| 状态机复杂度增加 | 低 | 新增 2 个状态，仅影响 orchestrator |

## 5. 与PRD对照表

| 验收标准 | 技术方案 | 实现位置 |
|---------|---------|---------|
| AC1: Monitor 3 Action 内告警 | GoalDriftDetector.drift_window=3 | `metacognition/triggers.py` |
| AC2: ReflAct 自动执行 | Reflection 插入 orchestrator 的 ReAct 循环 | `scheduler/orchestrator.py` + `scheduler/reflection.py` |
| AC3: 重复动作 5 周期检测 | RepetitionDetector.window_size=5 | `metacognition/triggers.py` |
| AC4: 关键决策 HITL | HITLManager + 决策节点配置表 | `metacognition/hitl.py` + `metacognition/triggers.py` |
| AC5: 错误分类 >75% | ErrorClassifier 规则匹配 + LLM 兜底 | `metacognition/classifier.py` |

## 6. 数据流

```
用户 → WebSocket → ChatStream → Orchestrator
                                    │
  ┌─────────────────────────────────┘
  │  ReAct Loop:
  │    Thought → Action → Observation
  │                    │
  │                    ▼ (NEW)
  │              Reflection 阶段
  │              · 调用 goal/verification 的对齐检查
  │              · 生成结构化 JSON
  │              · emit reflection_completed 事件
  │                    │
  │    ◄─── ─── ─── ───┘
  │
  │  (并行) EventBus ───▶ Monitor Agent
  │                          · 消费 action_* / reflection_* 事件
  │                          · 运行 TriggerEngine
  │                          · HITLManager 发送 WS 通知
  │                          · ErrorClassifier 记录分类
  │
  ▼
最终结果 → WebSocket → 前端 AgentOps 面板 + HITLModal
```

---

> **阶段门禁**：等待用户确认后进入阶段 3（编码实现）。
