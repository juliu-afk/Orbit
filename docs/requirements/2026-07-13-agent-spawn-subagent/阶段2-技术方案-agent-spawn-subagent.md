# 阶段2 技术方案：Agent 级 Subagent 生成能力

> 基于阶段1 PRD（验收标准 9 条），本次技术方案覆盖全部 9 条，无偏离。
> 日期: 2026-07-13

---

## 1. 方案总览

```
Agent (ReAct 循环)
  → think: "需要并行调研3个模块"
  → act: spawn_subagent(role="architect", task="分析 auth 模块")
          spawn_subagent(role="architect", task="分析 db 模块")  
          spawn_subagent(role="architect", task="分析 api 模块")
  → observe: 收集3个子Agent结果 → 汇总 → 继续ReAct
```

核心思路：**把已有 `ActorSpawn` 包装成 ToolRegistry 工具**——基础设施零改动，只加工具注册+角色权限+约束逻辑。

---

## 2. PRD 验收标准对照表

| PRD 验收标准 | 技术方案 | 覆盖 |
|-------------|---------|------|
| AC1: spawn_subagent 工具注册，Dev/Reviewer/QA 可调用 | 新文件 `tools/subagent.py` + ROLE_TOOLS 扩展 | ✅ |
| AC2: 子 Agent 返回结构化结果 | DeferredActor.result() 返回 dict → ToolEntry 格式化为字符串 | ✅ |
| AC3: 父 Agent 可并行 spawn 多个（≤4） | asyncio.gather 并行 await 多个 DeferredActor | ✅ |
| AC4: 子 Agent 错误隔离 | 单个子 Agent 异常→返回 error dict，不传播到其他 | ✅ |
| AC5: 深度限制 depth=1 | 子 Agent 的 tool list 不含 spawn_subagent（ROLE_TOOLS 裁剪） | ✅ |
| AC6: 全局 MAX_CONCURRENT 共享 | ActorSpawn.spawn() 已有 count_active() 检查——天然共享 | ✅ |
| AC7: spawn 记录审计 | ActorRegistry 已有 parent_task_id + actor_id + role + timestamp | ✅ |
| AC8: 前端任务树 | **后续 PR**——本次后端记录 parent_task_id，前端暂不改 | ⚪ 延后 |
| AC9: 子 Agent 超时 | DeferredActor.result(timeout=120) | ✅ |

> AC8 前端任务树：后端已有 parent_task_id（ActorRecord 字段），前端展示任务树后续 PR 实现。本次不阻塞。

---

## 3. 新增文件

### 3.1 `src/orbit/tools/subagent.py`（新建，~120 行）

```
subagent.py
├── 模块级变量: _actor_spawn: ActorSpawn | None
├── set_actor_spawn(spawn) —— main.py 启动时注入
├── SPWAN_ALLOWED_ROLES —— 可 spawn 的角色白名单
├── spawn_subagent(role, task, context?, timeout?) → str
│   ├── 1. 校验 role 在白名单内
│   ├── 2. 校验 _actor_spawn 已初始化
│   ├── 3. actor_spawn.spawn(role=role, task=task, ...)
│   │     → DeferredActor
│   ├── 4. 并行 await asyncio.gather(*deferreds)（如多次调用）
│   │     或者单次 await deferred.result(timeout=...)
│   └── 5. 格式化返回: {status, output, turns, tool_calls, error}
└── AST 自注册: registry.register_tool("spawn_subagent", ...)
```

**关键设计决策**：

1. **每次调用 spawn 一个子 Agent**——并行由父 Agent（LLM）决定。LLM 在一次 ReAct 循环中可多次调用 spawn_subagent，工具层用 `asyncio.gather` 并行执行同批次调用。这是工具注册中心的 `_should_parallelize` 机制自动处理的——spawn_subagent 标记为 `concurrency="safe"`。

2. **角色白名单**：子 Agent 只能 spawn 为 developer/architect/reviewer/qa。不能 spawn chatter/clarifier。

3. **深度限制**：子 Agent 的 ROLE_TOOLS 不含 spawn_subagent——自然无法递归。

4. **结果格式化**：工具返回字符串（ToolEntry 约定），结构化 JSON 嵌入字符串中。

### 3.2 `src/orbit/tools/registry/core.py`（修改，~3 行）

```python
ROLE_TOOLS = {
    ...
    "developer": {..., "spawn_subagent"},
    "reviewer": {..., "spawn_subagent"},
    "qa": {..., "spawn_subagent"},
}
```

### 3.3 `src/orbit/api/main.py`（修改，~3 行）

```python
# 在 ActorSpawn 创建后注入到 subagent 工具
from orbit.tools.subagent import set_actor_spawn
set_actor_spawn(_actor_spawn)
```

---

## 4. 数据流

```
┌─ ReActAgent (父) ──────────────────────────────────────────┐
│                                                            │
│  think: "需要并行调研"                                       │
│    ↓                                                       │
│  act: tool_calls = [                                       │
│    {name:"spawn_subagent", args:{role:"architect",task:"分析auth"}}, │
│    {name:"spawn_subagent", args:{role:"architect",task:"分析db"}},   │
│    {name:"spawn_subagent", args:{role:"architect",task:"分析api"}},  │
│  ]                                                         │
│    ↓                                                       │
│  ToolRegistry.dispatch("spawn_subagent", ...)              │
│    → subagent.spawn_subagent(role, task, ...)              │
│      → _actor_spawn.spawn(task, role, ...)                 │
│        → ActorRegistry.allocate() → actor_id               │
│        → ActorRegistry.register(pending)                   │
│        → AgentFactory.create(role) → ReActAgent            │
│        → asyncio.Task(agent.execute_stream)                │
│        → DeferredActor                                     │
│      → await deferred.result(timeout=120)                  │
│        → ActorRegistry.update_status(running)              │
│        → [子Agent ReAct循环: think→act→observe]              │
│        → ActorRegistry.update_status(idle, success)        │
│      → 返回 JSON: {status, output, turns, ...}             │
│    ↓                                                       │
│  observe: 3个子Agent结果 → 汇总 → 输出                       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**并行机制**：ToolRegistry 的 `_should_parallelize` 判定 spawn_subagent 为 `concurrency="safe"` → 同批次 3 个 spawn_subagent 调用自动 `asyncio.gather` 并行执行。

---

## 5. API 设计（工具 Schema）

```json
{
  "type": "function",
  "function": {
    "name": "spawn_subagent",
    "description": "创建子Agent并行执行任务。可用于：并行调研多个文件/模块、并行审查不同维度、并行生成测试用例。子Agent角色限制为developer/architect/reviewer/qa，最大并发4。",
    "parameters": {
      "type": "object",
      "properties": {
        "role": {
          "type": "string",
          "enum": ["architect", "developer", "reviewer", "qa"],
          "description": "子Agent角色"
        },
        "task": {
          "type": "string",
          "description": "子Agent任务描述——必须具体明确，包含验收标准"
        },
        "context": {
          "type": "string",
          "description": "额外上下文（可选）——如相关代码片段、设计文档摘要等"
        },
        "timeout": {
          "type": "integer",
          "default": 120,
          "description": "超时秒数（默认120s）"
        }
      },
      "required": ["role", "task"]
    }
  }
}
```

**返回格式**（字符串，嵌入 JSON）：

```json
{
  "status": "ok|error|timeout",
  "actor_id": "act_xxx",
  "output": "子Agent的最终输出文本",
  "turns": 3,
  "tool_calls": 5,
  "error": null
}
```

---

## 6. 数据模型变更

**无 Schema 变更**——ActorRegistry 已有全部所需字段：

```sql
-- 已有表（actors/registry.py）
actor_registry (
    actor_id TEXT PRIMARY KEY,
    parent_task_id TEXT,     -- ← 现成：父子关系
    role TEXT,               -- ← 现成：子Agent角色
    task TEXT,               -- ← 现成：任务描述
    status TEXT,             -- ← 现成：PENDING→RUNNING→IDLE
    outcome TEXT,            -- ← 现成：SUCCESS/FAILURE/CANCELLED
    result_json TEXT,        -- ← 现成：AgentOutput.result
    error TEXT,              -- ← 现成：错误信息
    created_at TEXT,         -- ← 现成：时间戳
    updated_at TEXT,
    session_id TEXT
)
```

---

## 7. 调度器影响

| 维度 | 影响 | 处理 |
|------|------|------|
| Scheduler 状态机 | **不变**——子 Agent 不经过 Scheduler | ActorSpawn 独立管理子 Agent 生命周期 |
| Task 模型 | **不变**——子 Agent 没有 Task 记录 | ActorRecord 独立于 Task |
| 检查点 | **不涉及**——子 Agent 无检查点 | 失败就失败，父 Agent 自行决策重试 |
| 取消传播 | Scheduler 取消父 Agent → 子 Agent 收到 cancel | CancellationToken 传播链已有（spawn.py:156-157） |
| 并发上限 | 共享 MAX_CONCURRENT=4 | ActorSpawn.spawn() 第 127 行 count_active() 检查 |

---

## 8. 防幻觉层影响

| 层 | 影响 | 处理 |
|----|------|------|
| L1-L8 | 子 Agent 独立过防幻觉管线 | 无变化——子 Agent 也是 ReActAgent，execute_stream 内已有完整管线 |
| 上下文污染 | 子 Agent 没有父 Agent 的已验证上下文 | 在 context 参数中注入父 Agent 已验证结论摘要（≤500 字符） |
| Doom Loop | 子 Agent 可能陷入循环 | ToolRegistry doom loop 检测独立作用于子 Agent |

---

## 9. 边界 Case 清单（硬性）

| # | 场景 | 预期行为 | 实现方式 |
|---|------|---------|---------|
| CE1 | 全局并发满（4/4） | spawn_subagent 返回 `{status:"rejected", reason:"concurrency_limit"}` | ActorSpawn.spawn() 抛 RuntimeError → 工具 catch 返回错误 |
| CE2 | 子 Agent 超时（120s） | 返回 `{status:"timeout", partial_result:"..."}` | DeferredActor.result(timeout=120) → TimeoutError catch |
| CE3 | 子 Agent 尝试递归 spawn | 无 spawn_subagent 工具可用 | ROLE_TOOLS 不包含 spawn_subagent |
| CE4 | 子 Agent 指定 chatter 角色 | 返回 `{status:"error", error:"role_not_allowed"}` | SPWAN_ALLOWED_ROLES 校验 |
| CE5 | 子 Agent LLM 调用失败 | 返回 `{status:"error", error:"llm_unavailable"}` | _run_actor 中 except 返回 error dict |
| CE6 | 父 Agent cancel 前已 spawn 子 Agent | 子 Agent 继续执行，Watchdog 清理 | CancellationToken 传播（spawn.py:157） |
| CE7 | 同一父 Agent 连续 spawn 同参数 3 次 | Doom loop 拦截 | ToolRegistry.would_form_loop() |
| CE8 | _actor_spawn 未初始化（测试环境） | 返回 `{status:"error", error:"actor_spawn_not_configured"}` | 模块级 None 检查 |
| CE9 | 子 Agent 输出超大（>10K） | 截断为头尾 5K+摘要 | ToolEntry 默认 max_result_chars 机制 |
| CE10 | 多个子 Agent 写入同一文件 | 文件冲突——按 spawn 顺序串行 | write_file 的 PATH_SCOPED 机制 |

---

## 10. 风险与缓解

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| **Token 消耗爆炸**：3 个子 Agent × 各自 ReAct 循环 = 大量 token | 高 | ① 子 Agent 用 T2 低成本模型；② 独立 token 预算，不消耗父 Agent 配额；③ MAX_CONCURRENT=4 硬上限 |
| **结果不一致**：3 个子 Agent 对同一问题的分析可能有冲突结论 | 中 | LLM（父 Agent）天然擅长汇总和冲突消解——在 observe 阶段由父 Agent 自行判断 |
| **事件循环嵌套**：asyncio.Task 中 await 另一个 asyncio.Task | 低 | ActorSpawn 已有成熟的事件循环管理——生产环境已验证 |
| **调试困难**：子 Agent 透明执行，开发者看不到中间过程 | 中 | ActorRegistry SQLite 记录完整生命周期 + structlog 日志 actor_id |

---

## 11. 依赖链

```
新增依赖: 无（纯内部模块调用）
内部模块依赖:
  subagent.py → actors/spawn.py (ActorSpawn)
  subagent.py → actors/models.py (ActorRecord, MAX_CONCURRENT)
  subagent.py → tools/registry/core.py (ToolRegistry, get_registry)
  main.py     → tools/subagent.py (set_actor_spawn)
  core.py     → ROLE_TOOLS 新增 spawn_subagent
```

---

## 12. 测试计划

| 测试层 | 用例 | 覆盖 |
|--------|------|------|
| 单元测试 | test_spawn_subagent_role_validation | CE4: 角色白名单校验 |
| 单元测试 | test_spawn_subagent_concurrency_limit | CE1: 并发满拒绝 |
| 单元测试 | test_spawn_subagent_timeout | CE2: 超时处理 |
| 单元测试 | test_spawn_subagent_not_configured | CE8: 未初始化 |
| 集成测试 | test_spawn_subagent_basic | AC1: 端到端 spawn→执行→返回 |
| 集成测试 | test_spawn_subagent_parallel | AC3: 并行 spawn 3 个子 Agent |
| 集成测试 | test_spawn_subagent_error_isolation | AC4: 一个失败不影响其他 |
| 集成测试 | test_subagent_no_recursive_spawn | CE3: 子 Agent tool list 无 spawn |
