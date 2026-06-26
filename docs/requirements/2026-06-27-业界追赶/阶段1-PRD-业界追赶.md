# PRD：业界追赶——四维工程全面升级（Phase 1-3）

> 版本: v1.0 | 日期: 2026-06-27 | 状态: 待确认 | Phase 1 先做
> 基于: `docs/开发计划/追赶参考/` 9 份研究文档（5 框架源码分析）

---

## 1. 背景

Orbit 在四维工程评分中得分 16/40，业界最佳 MiMo Code 37/40。

**目标**：分 3 阶段追上业界最佳水平（33/40）。

| 阶段 | 时间 | 维度 | 分数提升 |
|------|------|------|:--:|
| Phase 1 | Week 1-2 | Harness + Loop + Prompt | 16→23 |
| Phase 2 | Week 3-4 | Context + Memory + Dream | 23→30 |
| Phase 3 | Month 2 | Compose + Multi-engine + Security | 30→33 |

---

## 2. 用户故事

### P0

- **作为 DeveloperAgent**，我希望能读取项目文件、搜索代码、执行 Shell 命令，以便真正完成编码任务而不是只输出文本。
- **作为调度器**，我希望能让 Agent 进入 ReAct 循环（think→act→observe），多轮调用工具直到完成，而不是一次 LLM 调用就结束。
- **作为运维人员**，我希望 Agent 的 System Prompt 包含工具使用指南和禁止项，避免生成危险代码。

### P1（后续 PRD）

- 上下文压缩 + token 预算
- 文件记忆系统（MEMORY.md + checkpoint）
- /dream 自进化

### P2（后续 PRD）

- Compose 流水线 + 多引擎路由 + 安全权限

---

## 3. 验收标准

### AC1-5：工具层（对标 Hermes AST 自注册 + Claude Code 工具集）

| # | 标准 | 参考源码 |
|---|------|---------|
| AC1 | 实现 6 个核心工具：`read_file`, `write_file`, `edit_file`, `exec_command`, `grep`, `glob` | Claude Code leaked 43 tools, OpenCode 20 tools |
| AC2 | 工具通过 AST 自注册——文件底部 `registry.register()` 即自动发现，无需手动 import | Hermes `tools/registry.py:44` `discover_builtin_tools()` |
| AC3 | 工具参数用 JSON Schema 定义（LLM 可见），handler 与 schema 解耦 | Hermes 三层分离 |
| AC4 | `read_file`, `grep`, `glob` 可并发执行；`write_file`, `edit_file` 串行 | Hermes `tool_dispatch_helpers.py:104` 三类判定 |
| AC5 | Doom Loop 检测——连续 3 次同工具同参数 → 中断询问 | OpenCode `processor.ts:350` |

### AC6-8：ReAct 循环（对标 OpenCode runLoop + Claude Code while loop）

| # | 标准 | 参考源码 |
|---|------|---------|
| AC6 | DeveloperAgent 进入 think→act→observe 循环，最多 20 轮 | OpenCode `prompt.ts:1400` runLoop() |
| AC7 | 每轮：LLM 思考 → 选择工具 → 执行工具 → 结果反馈 → 继续或停止 | Claude Code while + tool_calls |
| AC8 | 4 种退出条件：正常完成 / 权限阻断 / 上下文溢出 / 步数上限 | OpenCode 4 exit conditions |

### AC9-10：Prompt 三层（对标 Hermes prompt_builder + Claude Code 7 层）

| # | 标准 | 参考源码 |
|---|------|---------|
| AC9 | 每个 Agent 的 system_prompt 拆为 stable/context/volatile 三层 | Hermes `prompt_builder.py` 三层缓存 |
| AC10 | stable 层包含：角色定义 + 工具列表 + 规则 + 禁止项 | Claude Code Layer 1-6 |

---

## 4. 交付计划——全部纳入，分 3 阶段

### Phase 1（P0·Week 1-2·生存底线）

| # | 验收标准 | 参考 |
|---|---------|------|
| AC1 | 6 核心工具（read_file/write_file/edit_file/exec_command/grep/glob）+ AST 自注册 | Hermes registry.py:44 |
| AC2 | tool_call JSON Schema 与 handler 三层解耦（schema/registry/handler） | Hermes 96工具文件 + ToolEntry dataclass |
| AC3 | 并发安全：只读并发（grep/glob/read）· 写入串行（write/edit）· 交互强制串行（exec） | Hermes tool_dispatch_helpers.py 三类判定 |
| AC4 | Doom Loop 检测（连续 3 次同工具同参数→中断） | OpenCode processor.ts:350 |
| AC5 | ReAct 循环：think→act→observe（max 20 turns, 10 退出原因, iteration_budget 90） | Hermes conversation_loop.py:496 + OpenCode runLoop() |
| AC6 | PromptBuilder 三层拼接（stable角色+工具+规则 / context项目信息 / volatile当前任务） | Hermes prompt_builder.py + Claude Code 7-layer 缓存边界 |
| AC6a | Shell 白名单（git/pytest/python/pnpm/uv/ls/cat）+ 23 validator 规则 | Claude Code Bash validators |
| AC6b | Tool output truncation（>10K chars → 头尾+摘要） | Claude Code 5-layer compression Layer 1 |
| **交付** | **Agent 能读代码→写代码→跑测试→闭环** | |

### Phase 2（P1·Week 3-4·追上行业）

| # | 验收标准 | 参考 |
|---|---------|------|
| AC7 | 上下文压缩：50%/85% 双阈值 + 8 步算法 + 子会话分叉（parent-child lineage） | Hermes context_compressor.py 2683行 |
| AC8 | Token 预算管理 + 5 层压缩管线（output truncation→message pruning→summary→sliding→dedup） | Claude Code 5-layer compression |
| AC9 | 文件记忆系统（MEMORY.md + checkpoint.md + progress.md + notes.md + SQLite FTS5 + 双向同步 reconcile + BM25 + CJK 分词） | MiMo Code memory/ 6 files + Hermes hermes_state.py 双FTS5 |
| AC10 | /dream 命令：5 阶段 LLM 合并 + 去重 + 验证路径 + 保持 <200行/10KB + 7天自动触发 | MiMo Code dream.txt + auto-dream.ts |
| AC11 | 会话持久化（SQLite + WAL 模式 + NFS 回退 + FTS5 全文搜索 + BM25 + 片段高亮） | Hermes hermes_state.py 5351行 |
| AC11a | Pre-compaction memory flush（静默 turn→写 daily log→NO_REPLY 不可见） | OpenClaw memory flush |
| AC11b | Checkpoint 边界算法（TAIL 10K-20K tokens + 5 条文本保护 + 可压缩工具结果擦除） | MiMo Code checkpoint.ts ~500行 |
| **交付** | **记忆持久化 + 自进化 + 长任务不崩溃** | |

### Phase 3（P2·Month 2·超越）

| # | 验收标准 | 参考 |
|---|---------|------|
| AC12 | Compose 流水线（spec-driven + 15 SKILL.md 技能 + spec review→code review 两阶段审查门禁） | MiMo Code compose/.bundle/ 15 skills |
| AC13 | Goal Judge 模型（Verdict schema·temperature=0·fail-open·MAX_GOAL_REACT=12·独立 judge 不干扰主Agent） | MiMo Code goal.ts ~150行 |
| AC14 | 子Agent 并行执行（allocate→register→fork→Deferred·SQLite actor registry·pending→running→idle 状态机·stale 5min 检测） | MiMo Code actor/spawn.ts 400行 + actor/registry.ts 300行 |
| AC15 | 多引擎路由（Claude Code `--permission-mode bypassPermissions --print` + Codex 子进程 + temp file prompt 管道） | OpenClaw code-agent plugin + agent_launch/agent_merge agent PR 等10工具 |
| AC16 | Worktree 隔离（6 策略: delegate/ask/off/manual/auto-merge/auto-pr·active→merged/dismissed 状态机·preview_safe/clean_safe 清理） | OpenClaw code-agent worktree |
| AC17 | 安全权限（7 层 deny-wins: profile→provider→global→agent→group→sandbox→depth·ML classifier 风险评分·23 Bash validators·AST shell parsing） | Claude Code 7-layer permission + OpenClaw 9-layer policy merge |
| AC18 | Schema 标准化 per-provider（Anthropic/OpenAI/Gemini/xAI/Mistral 5 适配器） | OpenClaw pi-tools.schema.ts 5 标准化函数 |
| AC19 | 流式处理（AgentLoop fullStream events: text-delta/tool-call/finish-step + 中断传播 + AbortSignal 包装） | OpenCode prompt.ts:1400 + OpenClaw pi-agent-core event stream |
| **交付** | **工业化 Agent 平台·多引擎·安全隔离·全流式** | |

## 5. 影响范围（Phase 1）

| 模块 | 改动 | 类型 |
|------|------|------|
| `src/orbit/tools/` | **新增**——ToolRegistry(含AST自注册) + 6个核心工具 | 新模块 |
| `src/orbit/agents/developer.py` | **重写**——从单次 execute() 改为 ReAct 循环 | 重大修改 |
| `src/orbit/agents/base.py` | **修改**——BaseAgent 增加 ReAct 循环基类 | 修改 |
| `src/orbit/prompt/builder.py` | **新增**——PromptBuilder 三层拼接 | 新模块 |
| `tests/unit/test_tools.py` | **新增**——工具层单元测试 | 新文件 |
| `tests/unit/test_react_loop.py` | **新增**——ReAct 循环单元测试 | 新文件 |
| `tests/unit/test_prompt_builder.py` | **新增**——Prompt 构建测试 | 新文件 |

---

## 6. 边缘情况

| 场景 | 处理 |
|------|------|
| 工具执行超时（30s） | 返回 timeout error → LLM 决定重试或换工具 |
| 文件路径在工作区外 | `wrapToolWorkspaceRootGuard()` 拒绝，对标 OpenClaw |
| Shell 命令含危险操作（rm -rf /） | 白名单 + 确认，对标 Claude Code Bash 23 validators |
| LLM 返回非 JSON tool call | retry 一次 → 失败则标记 error |
| 工具注册时 name 冲突 | custom > builtin > plugin，对标 MiMo Code 优先级 |
| Agent 超过 20 轮未完成 | 强制返回 + WARN，不阻塞 |

---

## 7. 待确认问题

1. Shell 工具是否允许任意命令？→ 建议白名单模式：`git`, `pytest`, `python`, `pnpm`, `uv`, `ls`, `cat`（对标 Claude Code Bash 23 validators）
2. 工具调用结果是否需要截断？→ 是，超过 10K chars 取头尾 + 摘要（对标 Claude Code Tool Output Truncation）
3. 本次是否包含 Anthropic cache_control 标记？→ 不含，P1 再做（需要先确定模型 provider 支持）
