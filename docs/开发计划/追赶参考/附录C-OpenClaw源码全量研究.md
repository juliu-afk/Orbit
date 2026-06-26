# 附录 C：OpenClaw 源码全量研究

> 来源: `github.com/badlogic/pi-mono` MIT (4 npm 包) + `github.com/openclaw/openclaw` MIT · 315K+ stars · TypeScript

---

## 1. Tool Calling——7 层工具管线

### 层叠结构

| 层 | 来源 | 示例 |
|---|------|------|
| 1. `tools.profile` | 基础预设 | `minimal`, `coding`, `messaging`, `full` |
| 2. `tools.byProvider.profile` | Provider 特定覆盖 | Claude 用 coding, Gemini 用 minimal |
| 3. `tools.allow/deny` | 全局 allow/deny | `allow: ["read","bash"]` |
| 4. `tools.byProvider.allow` | Per-provider | xAI 阻止 `web_search` |
| 5. `agents[].tools.allow` | Agent 特定 | Per-bot 工具限制 |
| 6. `agents[].tools.byProvider.allow` | Agent + provider 交集 | 精细控制 |
| 7. Group `tools.allow` | Channel/group 级 | Telegram vs Discord 策略 |
| 8. Sandbox policies | 沙箱环境 | 阻止 `exec` |
| 9. Subagent depth | 递归限制 | 最多 3 层 |

**核心原则**: "Explicit deny always wins; explicit allow overrides default deny."

### Schema 标准化（per-provider adaptation）

| 函数 | 目标 | 转换 |
|------|------|------|
| `patchToolSchemaForClaudeCompatibility()` | Anthropic/Claude | 移除不支持关键字，组合相关参数 |
| `cleanToolSchemaForGemini()` | Google Gemini | 剥离 `minLength/maxLength/pattern/format/const/enum` |
| `normalizeToolParameters()` | OpenAI | 展平 `oneOf` unions → 单属性 + 合并 required |
| `applyModelProviderToolPolicy()` | xAI/Grok | 删除 `web_search`（原生冲突） |
| `sanitizeToolCallId()` | Mistral | 截断为 9 个字母数字字符 |

### 工具包装链

```
exec → wrapToolParamNormalization → wrapToolWorkspaceRootGuard → wrapToolWithAbortSignal → wrapToolWithBeforeToolCallHook
```

| 包装器 | 文件 | 用途 |
|--------|------|------|
| `wrapToolParamNormalization()` | `pi-tools.schema.ts` | 强制字符串参数，处理 schema 异常 |
| `wrapToolWorkspaceRootGuard()` | `pi-tools.guard.ts` | 验证路径在工作区内 |
| `wrapToolWithAbortSignal()` | `pi-tools.abort.ts` | 传播 abort signal 用于取消 |
| `wrapToolWithBeforeToolCallHook()` | `pi-tools.before-tool-call.ts` | 触发插件 hook + loop 检测 + 指标 |

---

## 2. Agent Loop——6 阶段

### 引擎：4 npm 包嵌入

| 包 | 角色 |
|----|------|
| `@mariozechner/pi-ai` | 统一多 provider LLM 抽象（2000+ 模型, 15+ providers） |
| `@mariozechner/pi-agent-core` | 状态 Agent 运行时 + 工具调用 + 事件流 |
| `@mariozechner/pi-coding-agent` | 高级编码 Agent CLI/SDK（会话管理, 内置工具, 模型注册表） |
| `@mariozechner/pi-tui` | 终端 UI（OpenClaw 不用——用自己的 channel-based UI） |

### 6 阶段管线

**Phase 1: Intake** — Gateway RPC 标准化各 channel 消息 → 内部格式
**Phase 2: Context Assembly** — 加载会话历史（JSONL）+ System Prompt + memory + skills + 获取写锁
**Phase 3: Model Inference** — `Agent.prompt()` → `agentLoop()` → `streamSimple()` → 模型推理
**Phase 4: Tool Execution** — 策略过滤 → schema 标准化 → hook 链 → abort 传播 → 结果净化
**Phase 5: Streaming Replies** — assistant/text/tool/lifecycle 4 流实时推送
**Phase 6: Persistence** — 每交互写 JSONL → `.openclaw/agents/<id>/sessions/<sid>.jsonl`

### 内层引擎：pi-agent-core 双 while 循环

```
Outer loop: handle follow-up messages
  Inner loop: process turns (LLM call → tool execution → LLM call again)
    In each turn:
      1. Inject steering queue messages
      2. Call LLM via streamAssistantResponse()
      3. Process tool calls (parallel or sequential)
      4. Save point / prepareNextTurn hook
      5. Check shouldStopAfterTurn
      6. Check steering queue for interrupts
```

### 3 层 API 金字塔

| 层 | 文件 | 角色 |
|----|------|------|
| `agentLoop()` | `agent-loop.ts` | 纯 async generator，无状态，无持久化 |
| `Agent` 类 | `agent.ts` | 有状态，可订阅，steer/followUp 队列 + abort |
| `AgentHarness` | `agent-harness.ts` | 持久化，阶段状态机 (idle|turn|compaction|branch_summary|retry)，保存点 |

---

## 3. 记忆系统——极简双文件

### 文件布局

| 文件 | 加载策略 |
|------|---------|
| `MEMORY.md` | DM 会话开始时加载 |
| `memory/YYYY-MM-DD.md` | 今天+昨天的自动加载 |
| `SOUL.md` | Agent 身份/个性（可选启动文件） |
| `AGENTS.md` | 其他 Agent 信息（可选） |
| `USER.md` | 用户偏好（可选） |
| `TOOLS.md` | 工具文档（可选） |

### 混合搜索

- **BM25 (30%)** + **Vector (70%)** 组合评分
- **MMR re-ranking** lambda=0.7
- **时间衰减** 30 天半衰期（MEMORY.md 豁免）
- 存储：SQLite（嵌入式索引，非外部数据库）

### Pre-Compaction Memory Flush

```
触发: contextWindow - reserveTokensFloor(40K) - softThresholdTokens(4K)
行为: 静默 turn → 写 memory/YYYY-MM-DD.md → 回复 NO_REPLY 则不可见
限制: 每 compaction cycle 仅一次
跳过: workspace 只读或不可访问
```

### Compaction

```typescript
session.compact(customInstructions)  // 摘要对话历史为浓缩系统消息
```

---

## 4. Code-Agent 插件——子进程启动

### Claude Code 启动

```bash
claude --permission-mode bypassPermissions --print < "$PROMPT"
```
- `--permission-mode bypassPermissions` — 无交互审批
- `--print` — 结构化输出（非 TUI）
- Prompt 先写 temp 文件（避免 shell 转义 bug）
- 必须 `background:true`

### Session Lifecycle

```
Session Launch
  → Plan Generation (Agent 生成方案)
    → Approval (delegate/ask/approve)
      → Execution (隔离 worktree)
        → Monitoring (agent_output/agent_sessions)
          → Worktree Resolution (merge/PR/discard)
```

### Agent 工具

| 工具 | 用途 |
|------|------|
| `agent_launch` | 启动后台编码会话（workdir, permission_mode, worktree_strategy） |
| `agent_respond` | 回复/重定向/批准/升级权限 |
| `agent_sessions` | 列出活跃/近期会话 |
| `agent_output` | 读缓冲输出 |
| `agent_kill` | 停止/标记完成 |
| `agent_merge` | 合并 worktree 分支回 base |
| `agent_pr` | 创建/更新 GitHub PR |
| `agent_worktree_status` | worktree 生命周期状态 |
| `agent_worktree_cleanup` | 清理安全 worktrees |
| `goal_launch/status/edit/stop` | Verifier 风格 goal 循环 |

---

## 5. Worktree 隔离

### 策略

| 策略 | 行为 |
|------|------|
| `delegate` (默认) | Orchestrator 审查完成 worktree, 干净则 auto-merge, 否则升级给用户 |
| `ask` | 显示交互按钮: Merge / Open PR / Later / Discard |
| `off` | 无隔离，直接在 main 分支工作 |
| `manual` | Agent 自己管理分支 |
| `auto-merge` | 成功后自动合并无需审查 |
| `auto-pr` | 成功后自动开 GitHub PR |

### 生命周期状态机

```
active → pending decision → pr_open | merged | released | dismissed | no_change
```

### 清理

```typescript
agent_worktree_cleanup(mode: "preview_safe" | "clean_safe")
```

- `preview_safe` — 预览可清理
- `clean_safe` — 清理已解决沙箱（跳过活跃 PR/脏分支）

---

## 6. 可直接复制 vs 需适配

### 可直接复制

| 组件 | 来源 | 复杂度 |
|------|------|:--:|
| 双文件记忆 (MEMORY.md + daily log) | OpenClaw memory/ | 低 |
| Pre-compaction memory flush | OpenClaw | 低 |
| 工具包装中间件链 (纯函数组合) | `pi-tools.*.ts` | 低-中 |
| streamSimple/completeSimple 抽象 | `pi-ai/stream.ts` | 中 |
| Worktree 隔离 | code-agent plugin | 中 |
| agent_launch 子进程模式 | code-agent plugin | 中 |
| Goal launch 循环 | code-agent plugin | 中 |

### 需适配

| 组件 | 理由 |
|------|------|
| 9 层策略合并 | OpenClaw channel/group 概念在 Orbit 中不存在 |
| Schema 标准化（per-provider） | 需要 5 个 provider 适配函数，Orbit 先做 OpenAI-only |
| pi-agent-core 事件流 | 依赖 TypeScript Effect-TS，Orbit 需 Python 等效 |
| Session JSONL 持久化 | OpenClaw agent 目录结构，Orbit 有自己的存储 |
| pi-tui UI | OpenClaw 不用，Orbit 同理——有自己的驾驶舱 |
