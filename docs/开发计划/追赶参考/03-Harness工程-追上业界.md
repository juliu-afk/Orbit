# Harness Engineering——追上业界方案

> 参考源: Hermes, Claude Code, OpenCode, OpenClaw

---

## 一、业界最佳实践

### Hermes：工具自注册（AST 发现·最强设计）

```python
# tools/session_search_tool.py (文件末尾)
from tools.registry import registry

registry.register(
    name="session_search",
    toolset="session_search",
    schema=SESSION_SEARCH_SCHEMA,     # LLM 看到的 JSON Schema
    handler=lambda args, **kw: session_search(
        query=args.get("query", ""),
        db=kw.get("db"),              # runtime-injected, NOT in schema
        current_session_id=kw.get("..."),
    ),
    check_fn=check_session_search_requirements,  # 运行时可用性
)
```

**AST 自发现**——`import` 任何包含 `registry.register()` 的文件即注册：
```python
# 不需要手动 import list
# AST 分析扫描工具文件 → 发现 registry.register() → 自动导入 → 触发注册
```

**三层解耦**:
```
Schema Layer   ← LLM 看到什么（JSON function definitions）
Registry Layer ← 中央单例（name → schema + handler + check_fn）
Handler Layer  ← 实际执行函数
```

**两个分发路径**:
| 路径 | 用于 | 机制 |
|------|------|------|
| Registry Dispatch | 大多数工具（30+） | `registry.dispatch(name, args, **runtime_kwargs)` |
| Agent Loop Interception | todo/memory/session_search/delegate_task | Agent 状态（DB、session ID）不能暴露给 LLM |

### Claude Code：43 工具 + 延迟加载 + 并发安全

```
43 integrated tools:
  File: Read, Write, Edit, Grep, Glob
  Shell: Bash (23 validators, AST-level parsing)
  Web: WebFetch, WebSearch
  Agent: Agent (6 subagent types), Task, SendMessage
  MCP: MCP tools (on-demand via ToolSearch)
  Misc: TodoWrite, AskUserQuestion, Skill, NotebookEdit
```

**延迟加载**: 低频工具不在 prompt prefix 中，通过 `ToolSearch` 按需发现。
**并发安全**: `isConcurrencySafe` 分区——读写工具分离，避免冲突。

### OpenCode：20+ 工具 + Zod schema + Doom Loop 检测

```typescript
// 工具注册
const tools = [
  ...builtInTools,      // read, write, edit, grep, glob, bash
  ...mcpTools,          // MCP 协议工具
  ...structuredOutput,  // 结构化输出工具
].filter(t => agentHasPermission(t));

// Doom Loop 检测 (processor.ts:350-376)
if (last3Calls.every(c => c.tool === currentTool && c.args === currentArgs)) {
    promptUser("检测到死循环，是否继续？");
}
```

### OpenClaw：7 层工具管线

```
1. Base tools         — read, bash, edit, write (pi coding tools)
2. Custom replacements — exec/process 替代 bash（沙箱隔离）
3. OpenClaw tools     — messaging, browser, canvas, sessions, cron, gateway
4. Channel tools      — Discord, Telegram, Slack, WhatsApp 特定工具
5. Policy filtering   — 按 config, provider, agent, group, sandbox 过滤
6. Schema normalization — 修复 Gemini/OpenAI Schema 差异
7. AbortSignal wrapping — 可中断工具执行
```

---

## 二、Orbit 当前状态

```python
# ToolRegistry 只有 MCP 工具注册，没有文件系统/Shell/搜索工具
class ToolRegistry:
    def register(self, name, schema, handler): ...
    def dispatch(self, name, args): ...
```

**问题**：
- **零文件系统工具**——Agent 不能读/写/改代码
- **零 Shell 工具**——不能跑测试/构建/git
- **零搜索工具**——不能 grep/glob
- 没有自注册——工具需要手动 import
- 没有 check_fn——不知道工具是否可用
- 没有并发安全——不知道哪些工具可以并行

---

## 三、实施方案

### Phase 1：核心工具集（对标 Claude Code·3天）

```python
# src/orbit/tools/filesystem.py
@registry.register(
    name="read_file",
    toolset="filesystem",
    schema={
        "type": "function",
        "function": {
            "name": "read_file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 200},
                },
                "required": ["path"],
            },
        },
    },
    handler=read_file,
    check_fn=lambda: True,
)
async def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    """对标 Claude Code 的 Read 工具。"""

# write_file, edit_file, exec_command, grep, glob 同理
```

**第一批工具（对标 Claude Code 核心集）**:
| 工具 | 对标 | 功能 |
|------|------|------|
| `read_file` | Read | 读取文件片段 |
| `write_file` | Write | 写入文件 |
| `edit_file` | Edit | 精确字符串替换 |
| `exec_command` | Bash | Shell 命令（沙箱内） |
| `grep` | Grep | 正则搜索代码 |
| `glob` | Glob | 文件模式匹配 |

### Phase 2：AST 自注册（对标 Hermes·2天）

```python
# src/orbit/tools/registry.py
class ToolRegistry:
    @classmethod
    def discover(cls, paths: list[str]) -> None:
        """AST 扫描工具目录，自动 import 含 registry.register() 的文件。"""
        for path in paths:
            for file in Path(path).rglob("*.py"):
                if cls._has_register_call(file):
                    importlib.import_module(file.stem)

    @staticmethod
    def _has_register_call(file: Path) -> bool:
        """AST 检查文件顶层是否有 registry.register() 调用。"""
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == "register"):
                return True
        return False
```

### Phase 3：并发安全 + Doom Loop（对标 OpenCode·1天）

```python
class ToolRegistry:
    CONCURRENCY_SAFE = {"read_file", "grep", "glob", "exec_command"}
    # write_file/edit_file 不在列表中 → 串行

    async def execute_concurrent(self, calls: list[ToolCall]) -> list[ToolResult]:
        safe, unsafe = self._partition(calls)
        results = await asyncio.gather(*[self.dispatch(c) for c in safe])
        for c in unsafe:
            results.append(await self.dispatch(c))
        return results

    def detect_doom_loop(self, history: list[ToolCall]) -> bool:
        """最近 3 次调同一工具+同一参数 → 死循环。"""
        if len(history) < 3:
            return False
        last3 = history[-3:]
        return all(
            c.tool == last3[0].tool and c.args == last3[0].args
            for c in last3
        )
```

---

## 四、参考源码位置

| 项目 | 关键文件 | 行数 |
|------|---------|------|
| Hermes | `tools/registry.py` (AST self-registration) | ~200 |
| Hermes | `tools/session_search_tool.py` (register pattern) | ~50 |
| Claude Code | `tools/` dir (leaked, 43 tools) | ~2000 |
| OpenCode | `session/prompt.ts:resolveTools()` | ~100 |
| OpenCode | `session/processor.ts:350-376` (Doom Loop) | ~25 |
| OpenClaw | `src/agents/pi-tools.abort.ts` wrapToolWithAbortSignal | ~30 |
| OpenClaw | `src/agents/pi-tools.schema.ts` normalizeToolParameters | ~100 |
| OpenClaw | `src/agents/pi-tools.*.ts` 9-layer policy merge | ~200 |

---

## 五、OpenClaw 补充：工作区隔离 + 子进程 Agent 启动

### Worktree 隔离（对标 Git 沙箱）

```python
# src/orbit/sandbox/worktree.py
class WorktreeManager:
    """每个任务独立 git worktree，避免文件冲突。"""

    async def create(self, task_id: str) -> str:
        branch = f"agent/{task_id}"
        path = f"../.worktrees/{task_id}"
        await exec(f"git worktree add {path} {branch}")
        return path

    async def resolve(self, task_id: str, action: str):
        """merge | pr | discard"""
        states = {
            "merge": self._merge_and_cleanup,
            "pr": self._create_pr,
            "discard": self._remove_worktree,
        }
        return await states[action](task_id)
```

### 子进程 Agent 启动（对标 OpenClaw code-agent 插件）

```python
# src/orbit/runner/subprocess_agent.py
class SubprocessAgentRunner:
    async def launch_claude_code(self, task_id: str, prompt: str, cwd: str):
        # 1. 写 prompt 到临时文件（避免 shell 转义 bug）
        tmp = Path(f"/tmp/orbit-task-{task_id}.txt")
        tmp.write_text(prompt)

        # 2. 启动 Claude Code 子进程
        proc = await asyncio.create_subprocess_exec(
            "claude", "--permission-mode", "bypassPermissions", "--print",
            stdin=open(tmp),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        # 3. 流式读取输出
        async for line in proc.stdout:
            yield self._parse_output(line)

        # 4. 持久化结果
        self._save_result(task_id, proc.returncode)
```

---

## 六、Hermes 源码补充：AST 自注册 + 并行调度 + 压缩算法

### AST 自注册（`tools/registry.py:44` discover_builtin_tools）

```python
# 精确到行号的实现模式
def discover_builtin_tools():
    tools_dir = Path(__file__).parent
    for py_file in tools_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Attribute) and
                node.func.attr == "register" and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "registry"):
                # 文件包含 registry.register() → 导入触发注册
                importlib.import_module(f"tools.{py_file.stem}")
                break
```

### 并行调度决策（`agent/tool_dispatch_helpers.py:104` _should_parallelize_tool_batch）

三类工具：
- `_NEVER_PARALLEL_TOOLS = {"clarify"}` — 交互式，必须串行
- `_PARALLEL_SAFE_TOOLS = {"web_search","read_file","session_search",...}` — 只读，总是安全
- `_PATH_SCOPED_TOOLS = {"read_file","write_file","patch"}` — 路径不重叠时可并行

### 压缩算法核心（`agent/context_compressor.py` 行 742-2372）

关键常数：
- `threshold_percent = 0.50` — 50% 触发
- `_MIN_CTX_TRIGGER_RATIO = 0.85` — 退化为 85% 时
- `MINIMUM_CONTEXT_LENGTH = 64000` — 最小上下文
- `protect_first_n = 3` — 保护前 3 条消息
- `protect_last_n = 20` — 保护最后 20 条
- `summary_target_ratio = 0.20` — 摘要预算 20%
- `_MIN_SUMMARY_TOKENS = 2000` — 摘要下限
- `_SUMMARY_TOKENS_CEILING = 12000` — 摘要上限

压缩 8 步骤：工具输出修剪 → 找 head 边界 → token 预算向后遍历找 tail → LLM 摘要 → 组装 head+summary+tail → 边界对齐（不拆 tool_call/result 对）→ 用户消息锚定 → 会话分叉（创建子会话，记录 parent-child lineage）

### FTS5 会话搜索（`hermes_state.py:692-745`）

双 FTS5 索引：
```sql
-- 标准分词（英文+数字）
CREATE VIRTUAL TABLE messages_fts USING fts5(content);
-- trigram 分词（CJK/Thai 子串查询）
CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(content, tokenize='trigram');
```

### 迭代预算（`agent/iteration_budget.py` 62行）

- 主Agent: `max_iterations=90`，子Agent: `delegation.max_iterations=50`
- `execute_code` 调用退还预算（不消耗 iteration）
- 线程安全的 `consume()`/`refund()`
