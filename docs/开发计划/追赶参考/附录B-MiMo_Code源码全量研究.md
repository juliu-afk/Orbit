# 附录 B：MiMo Code 源码全量研究

> 来源: `github.com/XiaomiMiMo/MiMo-Code` MIT · `packages/opencode/src/` 504 TypeScript 文件 · Bun/Turborepo monorepo

---

## 1. Persistent Memory System（`packages/opencode/src/memory/` 6文件）

### 文件结构

| 文件 | 行数 | 职责 |
|------|:--:|------|
| `service.ts` | 115 | FTS5 search + BM25 + score floor filtering |
| `reconcile.ts` | 120 | 双向同步（disk→FTS 索引 + prune 已删除） |
| `fts.sql.ts` | 25 | FTS5 DDL schema |
| `fts-query.ts` | 45 | CJK token builder |
| `paths.ts` | 110 | 路径解析器 + scope/type 提取 |
| `index.ts` | — | 模块导出 |

### FTS5 Schema（可直接复用）

```sql
CREATE TABLE memory_fts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL,            -- global | projects | sessions
    scope_id TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL,             -- memory | checkpoint | progress | notes | feedback | project | reference | user
    body TEXT NOT NULL,
    fingerprint TEXT NOT NULL,      -- stat.size + "-" + stat.mtimeMs
    last_indexed_at INTEGER NOT NULL
);
CREATE INDEX idx_memory_scope ON memory_fts(scope, scope_id);
CREATE INDEX idx_memory_type ON memory_fts(type);
```

### 记忆文件布局

```
memory/global/MEMORY.md              ← 跨项目用户偏好
memory/projects/<pid>/MEMORY.md      ← 每项目持久知识
memory/sessions/<sid>/checkpoint.md  ← 会话检查点
memory/sessions/<sid>/notes.md       ← 自由笔记
memory/sessions/<sid>/tasks/<TID>/progress.md ← 任务进度
~/.claude/projects/<slug>/memory/**/*.md ← CC 互操作
```

### 双向同步（`reconcile.ts`）

```python
# Direction A: 新/变更文件 → FTS 索引
for md_file in root.rglob("*.md"):
    fingerprint = f"{stat.st_size}-{stat.st_mtime_ms}"
    if existing != fingerprint:
        body = read_text(md_file)
        db.upsert(path, body, fingerprint)

# Direction B: 已删文件 → 清理 FTS
for row in db.all():
    if not Path(row.path).exists():
        db.delete(row.path)
```

### BM25 搜索（`service.ts`）

- **Token 级 FTS5**: 标点剥离 → 每 token 双引号 `"token"` 包裹 → OR 连接
- **Score floor**: 相对比例（top hit × 0.15），过滤常见词
- **Over-fetch**: 3x 请求量（上限 50）

### CJK 分词（`fts-query.ts`）

```python
# 正则: [\p{L}\p{N}_]+ 匹配 Unicode 字母/数字/下划线（含 CJK）
tokens = re.findall(r'[\w]+', query, re.UNICODE)
fts_query = " OR ".join(f'"{t}"' for t in tokens)
```

---

## 2. /dream 命令——记忆自进化

### 5 阶段 LLM 驱动合并（`agent/prompt/dream.txt` ~150行）

1. **Phase 0 - Locate**: 搜索记忆文件，定位 SQLite DB 路径
2. **Phase 1 - Orient**: 读 MEMORY.md + notes.md + checkpoints + 列出近期会话
3. **Phase 2 - Gather**: 从检查点/进度/笔记提取候选事实
4. **Phase 3 - Verify**: 只读 SQLite 查询 `session`, `message`, `part`, `task`, `task_event`, `actor_registry` 表交叉验证
5. **Phase 4 - Consolidate**: 编辑 MEMORY.md（预定义章节: `## Rules`, `## Architecture decisions` 等）
6. **Phase 5 - Prune**: 保持 <200 行/10KB，验证路径（Glob），验证命名（Grep）

### 去重策略

- "Merge duplicates instead of appending"
- "Remove contradicted or obsolete entries when newer trajectory proves them stale"
- 相对日期转为绝对日期（YYYY-MM-DD）
- 会话 ID 保留在条目末尾：`[ses_xxx]` 供追溯

### 自动触发（`session/auto-dream.ts` ~120行）

| 命令 | 间隔 | 说明 |
|------|------|------|
| `/dream` | 7 天 | 记忆合并去重压缩 |
| `/distill` | 30 天 | 工作流发现打包 |

- 检查上次运行时间戳（SessionTable）
- 项目过新（<间隔）则跳过
- 最小 10 秒间隔防重复触发
- 生成子Agent 会话 "Auto Dream" / "Auto Distill"

---

## 3. Compose Pipeline（`skill/compose/.bundle/` 15 技能）

### 架构

Compose 模式 = skills-driven 编排框架：
- **15 个 compose 技能**，每个 `SKILL.md` + YAML frontmatter
- 技能类型: Rigid（TDD/debugging）vs Flexible（patterns）
- 技能优先级: process skills 先 → implementation skills 后

### 技能列表

| 技能 | 用途 |
|------|------|
| `compose:plan` | 写 specs-driven 实现方案 |
| `compose:subagent` | 按任务分发子Agent 执行 |
| `compose:debug` | 根因优先系统调试 |
| `compose:tdd` | 测试驱动开发 |
| `compose:execute` | 并行会话执行 |
| `compose:review` | 代码审查 |
| `compose:merge` | 合并工作流 |
| `compose:verify` | 验证工作流 |
| `compose:worktree` | 隔离工作区 |
| `compose:brainstorm` | 规格编写+视觉伴随 |
| `compose:new-skill` | 技能创建模板 |

### spec-driven 开发流程（`compose:subagent`）

```
1. Read plan → extract tasks → create task per plan task
2. Per task: dispatch implementer subagent → spec review → code quality review → mark done
3. Finish: final review → merge
```

---

## 4. Goal-Driven Stop with Judge Model

### Goal Service（`session/goal.ts` ~150行）

```typescript
const Verdict = z.object({
    ok: z.boolean(),
    impossible: z.boolean().optional(),
    reason: z.string(),
})
```

### Judge System Prompt

```
你是停止条件评估裁判。返回 JSON:
- {"ok": true, "reason": "<已完成的证据>"}
- {"ok": false, "reason": "<还缺什么>"}
- {"ok": false, "impossible": true, "reason": "<为什么无法完成>"}
```

### 安全设计

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_GOAL_REACT` | 12 | 硬上限，防死循环 |
| `MAX_PRE_REACT` | 3 | 子Agent 预反应上限 |
| `MAX_POST_REACT` | 3 | 子Agent 后反应上限 |
| Judge temperature | 0 | 确定性评估 |
| **Fail-open** | yes | judge 错误 = 当作已完成（不困住用户） |

### Goal Gate 流程（`session/prompt.ts:2050-2160`）

1. **Task Gate 先跑**（更便宜——检查是否有未完成任务）
2. **Goal Gate**（无活跃 goal 则跳过）
3. 编译完整 transcript → 送 judge 模型
4. 通过：清 goal，允许停止
5. 不通过 + 未超 MAX_GOAL_REACT: 注入合成 user turn（含 judge 理由），强制重新进入
6. 超上限: 清 goal，允许停止 + WARN

---

## 5. Subagent Spawning & Lifecycle

### Spawn 服务（`actor/spawn.ts` ~400行）

```typescript
interface SpawnInput {
    mode: SpawnMode          // "subagent" | "peer"
    sessionID: SessionID
    agentType: string
    task: string
    context: ContextMode     // "none" | "state" | "full"
    tools: ToolWhitelist
    background: boolean
    lifecycle?: Lifecycle
    forkContext?: ForkContext  // 继承上下文快照
}
```

### Spawn 流程

1. `ActorRegistry.allocateActorID` — 分配 actor ID
2. 注册 actor（status: "pending"）到 SQLite `ActorRegistryTable`
3. 创建元数据 session message（type: "actor"）
4. Fork work fiber（附着到 session lifecycle scope）
5. 返回 `SpawnResult` + `Deferred<AgentOutcome>`（异步结果追踪）

### Actor Registry（`actor/registry.ts` ~300行）

SQLite 状态机：
```
pending → running → idle
outcome: success | failure | cancelled
```

| 参数 | 值 |
|------|-----|
| stale 阈值 | 5 分钟 |
| 扫描间隔 | 60 秒 |
| 事件 | ActorRegistered, ActorStatusChanged |

### Turn 生命周期（`actor/turn.ts` 50行）

```typescript
const runTurn = (sessionID, actorID, work) =>
    Effect.uninterruptible(        // cleanup 总是执行
        Effect.gen(function* () {
            yield* reg.updateStatus(sessionID, actorID, { status: "running" })
            const exit = yield* work.pipe(Effect.interruptible, Effect.exit)
            yield* reg.updateStatus(sessionID, actorID, { status: "idle", outcome, error })
        })
    )
```

---

## 6. Context Manager（`session/compaction.ts` ~300行 + `session/checkpoint.ts` ~500行）

### Compaction

- `select()` — token 预算尾部选择
- `prune()` — 旧工具输出擦除
- `process()` — LLM 摘要（模板: Goal + Instructions + Discoveries + Accomplished + Relevant files）

### Checkpoint

| 参数 | 值 |
|------|-----|
| TAIL_MIN_TOKENS | 10000 |
| TAIL_MAX_TOKENS | 20000 |
| TAIL_MIN_TEXT_BLOCK_MESSAGES | 5 |
| 压缩目标 | 可压缩工具结果（read, bash, grep 等） |
| 输出 | checkpoint.md（checkpoint-writer 子Agent） |

---

## 7. Tool Registry（`tool/registry.ts` ~250行）

### Tool.define() 模式

```typescript
export const MemoryTool = Tool.define("memory", Effect.gen(function* () {
    const memory = yield* Memory.Service
    return {
        description: DESCRIPTION,   // 从 .txt 文件
        parameters: z.object({...}), // Zod schema
        execute: (args) => Effect.gen(function* () { /* impl */ })
    }
}))
```

### 注册优先级

1. **Built-in** ~20 工具（read, write, edit, bash, glob, grep, actor, memory, history, task, workflow, websearch, webfetch...）
2. **Custom** 扫描 `{tool,tools}/*.{js,ts}` → `import()` 加载
3. **Plugin** 从加载的 plugins 读取
4. **Priority**: custom > built-in > plugin

### Shell vs JSON 调用

- 每个工具声明 invocation style: `shell` | `json`
- Shell 模式解析自定义 DSL（如 `actor run general "desc" "prompt" --task T3`）
- `resolveInvocationStyle()` 每工具每会话选择风格
