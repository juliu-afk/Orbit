# 附录 D：Claude Code + Codex + OpenCode 源码研究

> 来源: Claude Code leaked source map v2.1.88 + OpenCode MIT (170K+ stars) + 社区逆向分析

---

## Claude Code

### System Prompt——7 层 + 缓存边界

```
[静态·可缓存 ~92% prefix reuse]
  Layer 1: Identity — "You are an interactive agent..."
  Layer 2: System Rules — 工具权限、注入警告
  Layer 3: Task Guidelines — Read-first、OWASP Top 10
  Layer 4: Actions/Safety — 可逆性、影响范围
  Layer 5: Tool Preferences — Read/Edit 优先于 Bash
  Layer 6: Tone & Style — 简洁、无 emoji、路径引用
  ← SYSTEM_PROMPT_DYNAMIC_BOUNDARY (缓存分割点)
[动态·每会话]
  Layer 7: Git status, CLAUDE.md, memory, MCP 指令, 语言
```

### Tool System——43 工具

| 类别 | 工具 |
|------|------|
| File | Read, Write, Edit, Grep, Glob, NotebookEdit |
| Shell | Bash (23 validators, AST-level shell parsing) |
| Web | WebFetch, WebSearch |
| Agent | Agent (6 subagent types), Task, SendMessage, TaskOutput, TaskStop |
| MCP | MCP tools (on-demand via ToolSearch) |
| Misc | TodoWrite, AskUserQuestion, Skill, EnterPlanMode, CronCreate/Delete, DesignSync |

**延迟加载**: 低频工具不在 prompt prefix 中，通过 `ToolSearch` 按需发现。
**并发安全**: `isConcurrencySafe` 分区——读写工具分离。

### Context Compression——5 层

```
Layer 1: Tool Output Truncation — 大输出取头尾 + 摘要
Layer 2: Message Pruning      — 保留最近 N 条，旧的摘要
Layer 3: Conversation Summary  — 定期摘要替换原始历史
Layer 4: Context Window Sliding — 近窗口上限时滑动
Layer 5: Semantic Dedup        — 去重工具调用结果
```

~200K token 预算：System prompt ~2K / History ~150K / Tool results ~30K / Response ~18K

### Agent Loop——while + tool_calls（极简核心 ~50行）

```typescript
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

无分类器、无 DAG、无 RAG pipeline——模型自己决定一切。

### Multi-Agent——6 Subagent 类型

| 类型 | 用途 |
|------|------|
| `general-purpose` | 通用复杂任务 |
| `Explore` | 只读代码搜索（按需 fan-out） |
| `Plan` | 架构设计 |
| `caveman:cavecrew-builder` | 1-2 文件精密编辑 |
| `caveman:cavecrew-investigator` | 只读代码定位（压缩输出 60%） |
| `caveman:cavecrew-reviewer` | diff/分支审查（每行 severity-tagged） |

### Security——7 层权限

```
Always Allow → Safe Pattern Auto → ML Classifier → Per-Session Allow →
Explicit Confirm → Directory Scoped → Global Deny
```

23 Bash validators + AST-level shell parsing + Parser Differential threat model + ML classifier（真实用户 accept/reject 模式训练）

### Hidden Features（82+ flags）

- **KAIROS** — 自主 agent 模式
- **KAIROS_DREAM** — dream/imagination 整合
- **COORDINATOR_MODE** — 多 agent 编排
- **TOKEN_BUDGET** — "+500K tokens" 扩展上下文
- **Undercover Mode** — 隐藏 AI 身份

---

## Codex CLI

### 上下文文件

- **AGENTS.md**（项目根目录）— 类似 CLAUDE.md
- 不支持 `@docs/` 语法
- 沙箱执行（内置）

### 工具集

标准文件系统 + Shell 工具集，与 Claude Code 类似但少于 Claude Code。

---

## OpenCode

### Agent Loop——runLoop()（`session/prompt.ts:1400` ~200行）

```typescript
while (true) {
    const systemPrompt = await collectSystemPrompt();
    const messages = buildMessages(systemPrompt, history);
    const result = await llm.stream({model, messages, tools});

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

### 4 个退出条件

| 条件 | 说明 |
|------|------|
| 正常完成 | LLM 返回 finish，原因非 `"tool-calls"` |
| 权限阻断 | 工具执行权限被拒 |
| 上下文溢出 | 自动触发 Compaction |
| 步数上限 | `maxSteps` 达到 |

### Doom Loop 检测（`session/processor.ts:350-376` ~25行）

```typescript
if (last3Calls.every(c => c.tool === currentTool && c.args === currentArgs)) {
    promptUser("检测到死循环，是否继续？");
}
```

### Multi-Agent 体系

| Agent | 模式 | 权限 | 用途 |
|-------|------|------|------|
| `build` | primary | 全部工具 | 默认开发 |
| `plan` | primary | 只读 + 计划文件 | 先方案后执行 |
| `general` | subagent | 除 todo 外全部 | 并行处理 |
| `explore` | subagent | 只读 | 快速代码导航 |
| `scout` | subagent | 仓库研究 | 依赖分析+文档 |
| `compaction` | primary(hidden) | 全部 deny | 上下文压缩专用 |

### Tool System——20+ 内置工具

**注册**: `内置工具 → MCP 工具 → 结构化输出工具 → Agent 权限过滤`

| 类别 | 工具 |
|------|------|
| 文件 | `read`, `write`, `edit` |
| 搜索 | `grep`, `glob` |
| 系统 | `bash` |
| 网络 | `webfetch`, `websearch` |
| Agent | `task` (子Agent 调度) |
| 追踪 | `todowrite` |
| 技能 | `skill` |

所有工具统一 `Tool` 接口 + Zod schema 参数验证。

### System Prompt 拼接

```typescript
const systemPrompt = [
    currentDirectory,         // 当前工作目录
    systemEnvironment,        // OS/Shell 信息
    globalAgentsMd,           // ~/.config/opencode/AGENTS.md
    projectAgentsMd,          // 项目 AGENTS.md 或 CLAUDE.md
    skillDescriptions,        // 200+ 内置技能模板
    providerBasePrompt,       // 模型厂商默认 prompt
].join("\n");
```

### 上下文压缩

```
保留最近 2 轮对话 (tail)
→ 将旧消息发给 LLM 生成结构化摘要
→ 摘要替代原始消息
→ 历史加载时自动跳过被压缩部分
```

### 技术栈

| 技术 | 用途 |
|------|------|
| TypeScript + Bun | 核心运行时 |
| Effect-TS | 函数式副作用管理 + 依赖注入 |
| Vercel AI SDK | 统一 75+ LLM 提供商接口 |
| Hono | HTTP API 框架 |
| SolidJS | Web 前端 |
| Tauri | 跨平台桌面应用 |
| Drizzle + SQLite | 会话数据持久化 |
| Zod | Schema 验证 |
| Bubble Tea (Go) | TUI 终端界面 |

---

## 对比总结：Orbit 可复制的工具调用模式

| 框架 | 工具注册 | 并发 | 权限 | 最值得学 |
|------|---------|------|------|---------|
| Hermes | **AST 自发现**（最佳） | ThreadPool(8) + 三类判定 | check_fn | 自注册 + 三层解耦 |
| OpenClaw | 9 层 merge | abort wrapper | **deny wins** | 包装链 + schema 标准化 |
| Claude Code | 43 工具延迟加载 | isConcurrencySafe 分区 | **7 层 + ML classifier** | 延迟加载 + 并发安全分区 |
| OpenCode | Zod schema 统一接口 | subagent fan-out | Agent 权限过滤 | Doom Loop 检测 |

**Orbit 最佳路径**: Hermes 的 AST 自注册 + OpenClaw 的包装链 + OpenCode 的 Doom Loop + Claude Code 的延迟加载。
