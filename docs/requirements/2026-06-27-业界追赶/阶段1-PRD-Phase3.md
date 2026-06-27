# PRD：业界追赶 Phase 3——Compose + Multi-engine + Security + Streaming

> 版本: v1.0 | 日期: 2026-06-27 | 状态: 待确认
> 基于: `阶段1-PRD-业界追赶.md` Phase 3 需求 (AC12-AC19) + 附录B/C/D 源码研究

---

## 1. 背景

Phase 1: Agent 能读→写→跑测试——闭环
Phase 2: 记忆持久化 + 自进化 + 长任务不崩溃

Phase 3 目标：从"单 Agent 工具箱"升级到"工业化 Agent 平台"——多 Agent 协作、多引擎路由、安全隔离、全流式。

**分数**: 30 → 33 (+3, 最难的 3 分)
**时间**: Month 2（按总索引估算 ~2 周）

---

## 2. 用户故事

### P0（核心架构）

- **作为项目负责人**，我希望能写一个 spec 文件，Agent 自动拆任务→并行分派→审查→合并，完成端到端开发。
- **作为开发者**，我希望 2+ 子 Agent 并发探索不同方案，Goa​​l Judge 判定最佳，合并输出。
- **作为安全管理员**，我希望每层 Agent 有独立权限边界，文件路径限制在工作区内，Shell 命令白名单。

### P1（平台增强）

- **作为运维人员**，我希望能同时启动 Claude Code CLI / Codex CLI 子进程，利用外部引擎处理任务。
- **作为前端开发者**，我希望驾驶舱看到 Agent 思考过程实时流（text-delta / tool-call / finish-step），不是转圈等到结束。

### P2（深度强化）

- **作为框架开发者**，我希望新增 LLM provider 时只需写一个 schema 适配器，工具定义自动映射。
- **作为系统管理员**，我希望 git worktree 隔离每个 Agent 工作区，auto-merge 干净结果，脏结果升级人工。

---

## 3. 验收标准（分 4 组）

### 组 1：流式 + Schema 标准化（AC18-AC19）— 3 天 · 基础层

| # | 标准 | 参考 |
|---|------|------|
| AC19.1 | AgentLoop 流式事件：text-delta / tool-call / finish-step / error | OpenCode runLoop events |
| AC19.2 | ReActAgent.execute() → async generator `execute_stream()` | 现有 react_agent.py 重构 |
| AC19.3 | AbortSignal 包装：CancellationToken 传播，cleanup 总是执行 | OpenClaw wrapToolWithAbortSignal |
| AC19.4 | 驾驶舱 SSE 端点 `/api/v1/agent/{id}/stream` | 复用现有 ws/ |
| AC19.5 | 流式中断：用户取消 → CancellationToken.set() → Agent 下轮检查 | 交互可用性 |
| AC18.1 | ProviderAdapter base class：`normalize_tool_schema()` / `normalize_response()` | OpenClaw pi-tools.schema.ts |
| AC18.2 | Anthropic + OpenAI adapter 实现（Gemini/xAI/Mistral later） | 5 标准化函数 |
| AC18.3 | 多 LLM provider 路由增强——模型选择策略（按任务/成本/速度） | 扩展 gateway/ + RouterAgent (Step 2.3) |

> **为何流式先做**：Compose + 子Agent 均依赖 ReActAgent 接口。流式改 async generator 后，Compose 基于新接口构建，避免二次重构。

### 组 2：子Agent 并发 + Goal Judge（AC13-AC14）— 4 天

| # | 标准 | 参考 |
|---|------|------|
| AC14.1 | ActorRegistry：SQLite 状态机 `pending→running→idle`，outcome: success/failure/cancelled | MiMo Code actor/registry.ts |
| AC14.2 | ActorSpawn：allocate ID → register → fork fiber → Deferred result | MiMo Code actor/spawn.ts |
| AC14.3 | stale 检测：5 分钟无状态变更 → 标记 zombie + 清理 | 同上 |
| AC14.4 | 子Agent 并发限制：最多 4 并行（min(16, cpu-2) 可配置） | Claude Code subagent cap |
| AC14.5 | Actor 间通信：message bus 传递 TaskContext（复用现有 communication/） | 现有消息总线 |
| AC13.1 | GoalJudge：Verdict schema `{ok, impossible, reason}`，temperature=0 | MiMo Code goal.ts |
| AC13.2 | fail-open 安全：judge 出错 = 当作完成，不困住用户 | 同上 |
| AC13.3 | MAX_GOAL_REACT=12 硬上限 + 超过则清 goal + WARN | 同上 |
| AC13.4 | Task Gate（便宜预检）→ Goal Gate（LLM judge）两级 | 同上 |

> **为何子Agent 先于 Compose**：Compose:subagent 技能依赖 ActorSpawn/ActorRegistry。子Agent 是 Compose 的执行基座。

### 组 3：Compose 流水线（AC12）— 5 天

| # | 标准 | 参考 |
|---|------|------|
| AC12.1 | SKILL.md 格式：YAML frontmatter (name/description/phase/tools) + markdown body | MiMo Code compose/.bundle/ |
| AC12.2 | 6 个 compose 技能：plan / subagent / debug / tdd / review / verify | MiMo 15 skill 子集 |
| AC12.3 | spec-driven 流程：read spec → extract tasks → dispatch via ActorSpawn → review → merge | compose:subagent |
| AC12.4 | 两阶段审查门禁：spec review（方案审）→ code quality review（代码审） | MiMo compose 门禁 |
| AC12.5 | ComposeOrchestrator 继承现有 Orchestrator，复用 DAG + 检查点 | 现有 scheduler/ |
| AC12.6 | SKILL.md 通过 AST 自发现加载（复用 tools/registry.py 模式） | 现有 ToolsRegistry.discover() |

### 组 4：Worktree 隔离 + 安全权限（AC16-AC17）— 3 天

| # | 标准 | 参考 |
|---|------|------|
| AC16.1 | WorktreeManager：git worktree add → 6 策略全做 (delegate/ask/off/manual/auto-merge/auto-pr) | OpenClaw code-agent worktree |
| AC16.2 | 状态机：active → pending_decision → pr_open/merged/released/dismissed/no_change | 同上 |
| AC16.3 | 清理：preview_safe / clean_safe 两级 | 同上 |
| AC17.1 | **5 层 deny-wins**：agent_role → tool_category → path_scope → sandbox → global_deny | Claude Code 7 层精简 |
| AC17.2 | workspace root guard：文件操作 Path.resolve() 必须在 project_root 内 | OpenClaw wrapToolWorkspaceRootGuard |
| AC17.3 | 23 Bash validator 规则（复用 Phase 1 shell.py 白名单 + 新增危险模式检测） | Claude Code Bash validators |

> **5 层 vs 7 层**：去掉 ML classifier（Orbit 不需用户行为训练）和 per-session allow（开发者场景会话级没必要），加 path_scope（安全关键）。deny-wins 仍然是核心原则。

---

## 4. 分组优先级与交付计划

| 组 | 内容 | AC | 时间 | 依赖 |
|---|------|:--:|:--:|---|
| **1** | 流式 + Schema | AC18-AC19 | 3天 | 现有 react_agent/gateway |
| **2** | 子Agent + Goal Judge | AC13-AC14 | 4天 | 组 1 流式接口 |
| **3** | Compose 流水线 | AC12 | 5天 | 组 2 子Agent 框架 |
| **4** | Worktree + 安全权限 | AC16-AC17 | 3天 | 独立（git + 工具层） |

**交付顺序**：1→2→3→4（每次合并独立 PR，Approval 后进下一组）

```
组1 流式基础 ──→ 组2 并行执行 ──→ 组3 编排流水线 ──→ 组4 安全加固
  3天              4天              5天              3天
```

---

## 5. 影响范围

### 新模块（7 个包）

| 模块 | 对应 AC | 文件数 | 组 |
|------|:--:|:--:|:--:|
| `src/orbit/stream/` | AC19 | 4 (events/cancellation/sse/broadcaster) | 1 |
| `src/orbit/actors/` | AC14 | 4 (registry/spawn/state/turn) | 2 |
| `src/orbit/goal_judge/` | AC13 | 3 (judge/gate/verdict) | 2 |
| `src/orbit/compose/` | AC12 | 8 (parser/orchestrator/skills/ + 6 个 SKILL.md) | 3 |
| `src/orbit/worktree/` | AC16 | 3 (manager/strategies/cleanup) | 4 |
| `src/orbit/security/` | AC17 | 4 (permission/guard/validators/classifier) | 4 |

### 修改模块

| 模块 | 改动 | 组 |
|------|------|:--:|
| `src/orbit/agents/react_agent.py` | async def → async generator (AC19) | 1 |
| `src/orbit/agents/factory.py` | 适配流式 Agent 创建 | 1 |
| `src/orbit/gateway/schemas.py` | ProviderAdapter + normalize (AC18) | 1 |
| `src/orbit/gateway/client.py` | 多 provider schema 适配 + 路由策略 | 1 |
| `src/orbit/scheduler/orchestrator.py` | Compose 分发钩子 + ActorSpawn (AC12/AC14) | 2/3 |
| `src/orbit/tools/registry.py` | 权限包装链挂载 (AC17) | 4 |
| `src/orbit/tools/filesystem.py` | workspace root guard (AC17) | 4 |
| `src/orbit/tools/shell.py` | 23 validator 规则补全 (AC17) | 4 |
| `src/orbit/sessions/registry.py` | Actor session 追踪 | 2 |
| `src/orbit/ws/` | SSE 端点 `/api/v1/agent/{id}/stream` | 1 |
| `frontend/` | 流式驾驶舱组件 (ChatStream) | 1 |

> AC15 多引擎子进程 → 取消。改为 LLM provider 路由增强，合并到 AC18 gateway/ 改动。

---

## 6. 边缘情况

| 场景 | 处理 |
|------|------|
| Compose spec 格式错误 | SKILL.md YAML parse 失败 → 返回明确错误 + 行号 |
| 子Agent 死锁 (2+ 互相等) | stale 5min 检测 → 标记 zombie → 超时 kill |
| Goal Judge 连续判定失败 | 3 次 judge 均失败 → 人工介入 |
| 外部引擎 (Claude Code) 未安装 | 健康检查失败 → 降级到 Orbit 内置 ReActAgent |
| git worktree 磁盘空间不足 | 创建失败 → 回退到 off 策略（主分支直接工作） |
| 流式连接断开 | CancellationToken 传播 → 子Agent 清理 → 部分结果保留 |
| 流式 generator 被关闭 | finally 块确保资源释放（对标 Effect.uninterruptible） |
| 权限层冲突 (role.allow ∩ global.deny) | deny wins（显式拒绝优先） |
| Provider schema 不兼容新参数 | adapter 跳过未知字段 + WARN 日志 |
| Worktree 磁盘空间不足 | 创建失败 → 回退到 off 策略（主分支直接工作） |
| SKILL.md YAML 解析失败 | 返回 `{error, line, reason}` 不阻塞其他技能 |
| Goal Judge 连续误判 | 3 次 judge 均 impossible → 清 goal + 人工介入 |
| Actor deadlock (2+ 互相等) | stale 5min 检测 → 标记 zombie + kill |
| ReActAgent 旧同步 API 调用方 | `execute()` 保留为 wrapper，内部调 `execute_stream()` 收集结果 |

---

## 7. 技术参考映射

| AC | 主要参考 | 源码文件 |
|----|---------|------|
| AC12 | MiMo Code | `skill/compose/.bundle/*/SKILL.md` |
| AC13 | MiMo Code | `session/goal.ts:150`, `session/prompt.ts:2050-2160` |
| AC14 | MiMo Code | `actor/spawn.ts:400`, `actor/registry.ts:300` |
| AC16 | OpenClaw | `code-agent` worktree strategies |
| AC17 | Claude Code + OpenClaw | 7-layer permission + 9-layer policy merge |
| AC18 | OpenClaw | `pi-tools.schema.ts` 5 normalize functions |
| AC19 | OpenCode + OpenClaw | `runLoop` events + `pi-agent-core` event stream |

> AC15 (多引擎子进程) 已取消——Orbit 自身有完整 Agent 循环，改为 LLM provider 路由增强并入 AC18。

---

## 8. 确认结果

| # | 问题 | 结论 |
|---|------|------|
| 1 | 分组独立合并 | ✅ 组 1→2→3→4，每组独立 PR merge |
| 2 | 多引擎子进程 | ✅ 取消——改为纯 LLM provider 路由增强（AC18） |
| 3 | Worktree 6 策略 | ✅ 全做：delegate/ask/off/manual/auto-merge/auto-pr |
| 4 | 流式 | ✅ 组 1 先做——ReActAgent.execute() → async generator |
| 5 | Schema adapter | ✅ Anthropic + OpenAI 两个，后续扩展 |
| 6 | 安全层数 | ✅ **5 层**：agent_role/tool_category/path_scope/sandbox/global_deny |
| 7 | 测试策略 | ✅ 每模块 ≥5 unit + ≥1 integration，全量回归保留 |

---

## 9. 下一步

用户确认后 → 进入阶段 2（组 1 技术方案——流式 + Schema）。
