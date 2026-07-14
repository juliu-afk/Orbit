# 阶段 1 PRD — 接线冲刺：Orbit 差距闭合

> 日期：2026-07-15 | 基于「Orbit vs OpenCode 穷尽架构对比报告」
> 基线：24 维度 × 92 项审计，29 P0 + 50 P1 + gepa/episodic

## 1. 背景

OpenCode 穷尽解构后发现 Orbit 核心矛盾：**439 模块存在，但 60% 没接入主执行路径**。用户实际体验中表现为"鬼打墙""回复丢失""长对话崩溃""LLM 挂了无感知"。

## 2. 分 Phase 交付

### Phase A：基本可用（1-2 天，11 P0）

**目标**：消息不丢、会话不冲突、对话能恢复。

| # | P0 项 | 涉及文件 |
|----|-------|---------|
| A1 | 回复在 _send 前持久化 | chat.py |
| A2 | role 统一为 "assistant" | chat.py + sessions/registry.py |
| A3 | 会话锁——同 session 串行 | chat.py (asyncio.Lock per session) |
| A4 | get_messages 无硬上限 | sessions/registry.py |
| A5 | 会话恢复 > 50 条 | sessions/registry.py |
| A6 | 结构化输出入 session | chat.py + chat_messages 表 |
| A7 | 消息粒度——Part 基础类型 | sessions/models.py (TextPart/ToolPart 最小集) |
| A8 | 工具调用记录持久化 | sessions/models.py + registry.py |
| A9 | _send 前创建占位消息 | chat.py (参照 OpenCode) |
| A10 | 会话生命周期事件 | events/bus.py → session.created/idle/error |
| A11 | 自动会话标题生成 | chat.py (T2 模型调一次) |

### Phase B：上下文不崩（2-3 天，8 P0）

**目标**：长对话不超窗口、压缩后能继续、压缩接入全 Agent。

| # | P0 项 | 涉及文件 |
|----|-------|---------|
| B1 | ContextCompressor 接入 Chatter | chatter.py execute() |
| B2 | ContextCompressor 接入 Clarifier | clarifier/agent.py execute() |
| B3 | 压缩后自动恢复——replay 最后 user 消息 | compressor.py + chatter.py |
| B4 | 压缩触发——每轮 loop 前检查 | chatter.py + clarifier/agent.py |
| B5 | 流内压缩——Stream.takeUntil | stream/ + processor |
| B6 | 压缩后消息过滤——filterCompactedEffect | sessions/registry.py |
| B7 | 工具输出轮次保护——prune 保护最近 2 轮 | pipeline.py |
| B8 | 摘要模板补 Constraints + NextSteps | compressor.py |

### Phase C：Agent 循环鲁棒（3-5 天，7 P0）

**目标**：LLM 失败有重试、死循环有拦截、权限可控制。

| # | P0 项 | 涉及文件 |
|----|-------|---------|
| C1 | LLM 失败重试——指数退避 + retry-after | gateway/client.py |
| C2 | Provider 降级——主不可用切备选 | gateway/routing.py |
| C3 | 运行时权限工具确认 | tools/registry/core.py (confirm 回路全局接入) |
| C4 | 退出条件双重校验 | react_agent/agent.py |
| C5 | Doom Loop → 用户交互而非直接 abort | react_agent/agent.py |
| C6 | System Reminder 每轮注入 | prompt/builder.py |
| C7 | .env 文件保护——filesystem 工具拒绝读取 | tools/filesystem.py |

### Phase D：跨 Agent 完整 + Hook（2-3 天，3 P0）

**目标**：SubAgent 上下文完整、插件可扩展。

| # | P0 项 | 涉及文件 |
|----|-------|---------|
| D1 | SubAgent 上下文——传 session_id + handoff_summary | actors/spawn.py + runner.py |
| D2 | Hook 系统——6 个基础 hook 点 | events/bus.py + tools/registry/core.py |
| D3 | Plugin 接口——JS/TS 可编程扩展 | 新文件 + opencode.json 式配置 |

### Phase E：P1 冲刺（后续，50 项）

逐步补齐压缩策略、Agent 循环细节、前端体验、记忆系统、测试覆盖。

### Phase F：gepa/episodic 深接

进化引擎和情景记忆从 2 引用 → 全链路接入。

## 3. 成功指标

| 指标 | 当前 | Phase A | Phase A-D |
|------|------|---------|----------|
| P0 闭合率 | 0/29 | 11/29 | 29/29 |
| 基本可用 | ❌ | ✅ | ✅ |
| 工程完整 | ❌ | ❌ | ✅ |

## 4. Non-Goals

- ❌ 不改架构——接线而已，不改模块内部逻辑
- ❌ 不加新概念——所有功能在现有模块内实现
- ❌ 不引入新依赖

## 5. 待确认

1. Phase A 先做？确认后进入阶段 2 技术方案
