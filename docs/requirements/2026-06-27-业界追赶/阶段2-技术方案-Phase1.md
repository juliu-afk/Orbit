# 技术方案：业界追赶 Phase 1——工具层 + ReAct 循环 + Prompt 三层

> 日期: 2026-06-27 | 基于阶段1 PRD（AC1-AC6b·8条）

---

## 1. 需求回顾

基于阶段1 PRD，Phase 1 覆盖 8 条 AC。交付目标：Agent 能读代码→写代码→跑测试→形成闭环。

---

## 2. 架构总览

```
                    ┌──────────────────┐
                    │   PromptBuilder  │  ← AC6: stable/context/volatile 三层
                    └────────┬─────────┘
                             │ system_prompt
                    ┌────────▼─────────┐
                    │   ReActAgent     │  ← AC5: think→act→observe 循环
                    │   (BaseAgent)    │
                    └────────┬─────────┘
                             │ tool_calls
                    ┌────────▼─────────┐
                    │   ToolRegistry   │  ← AC1-AC3: AST自注册+JSONSchema+并发
                    │   read | write   │
                    │   edit | exec    │
                    │   grep | glob    │
                    └──────────────────┘
```

## 3. 新增/修改文件

| 文件 | 类型 | 行数预估 | 职责 |
|------|------|:--:|------|
| `src/orbit/tools/registry.py` | 重写 | ~300 | AST自注册 + JSON Schema + check_fn + 并发标记 |
| `src/orbit/tools/filesystem.py` | 新增 | ~150 | read_file, write_file, edit_file |
| `src/orbit/tools/shell.py` | 新增 | ~100 | exec_command(白名单) |
| `src/orbit/tools/search.py` | 新增 | ~80 | grep, glob |
| `src/orbit/agents/react_agent.py` | 新增 | ~200 | ReActAgent 基类——think→act→observe 循环 |
| `src/orbit/agents/factory.py` | 修改 | ~100 | DeveloperAgent 继承 ReActAgent |
| `src/orbit/prompt/builder.py` | 新增 | ~120 | PromptBuilder stable/context/volatile 三层 |
| `tests/unit/test_tools.py` | 新增 | ~200 | 工具层测试 |
| `tests/unit/test_react_agent.py` | 新增 | ~200 | ReAct 循环测试 |
| `tests/unit/test_prompt_builder.py` | 新增 | ~80 | Prompt 构建测试 |

---

## 4. 详细设计

### 4.1 ToolRegistry——AST 自注册（AC1-AC3）

```python
# src/orbit/tools/registry.py 重写
class ToolRegistry:
    """工具注册中心——AST 自发现 + JSON Schema + 并发安全 + Doom Loop 检测。"""
    _instance = None
    _tools: dict[str, ToolEntry] = {}
    _lock = threading.RLock()

    # ── 自注册入口 ──
    def register(self, name: str, toolset: str, schema: dict,
                 handler: Callable, check_fn: Callable | None = None,
                 concurrency: str = "safe"):  # "safe" | "serial" | "never_parallel"
        ...

    # ── AST 自发现 ──
    @classmethod
    def discover(cls, paths: list[str]) -> None:
        """对标 Hermes discover_builtin_tools()——AST 扫描 + 自动导入。"""
        for path in paths:
            for f in Path(path).rglob("*.py"):
                if f.name.startswith("_"): continue
                tree = ast.parse(f.read_text())
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and
                        isinstance(node.func, ast.Attribute) and
                        node.func.attr == "register"):
                        importlib.import_module(f"orbit.tools.{f.stem}")
                        break

    # ── 并发安全判断（对标 Hermes 三类判定） ──
    _NEVER_PARALLEL = {"exec_command"}       # 交互式，必须串行
    _PATH_SCOPED = {"write_file", "edit_file"}  # 同路径串行，不同路径可并行
    # 其余默认 safe——可并发

    def _should_parallelize(self, calls: list[ToolCall]) -> tuple[list, list]:
        """对标 Hermes _should_parallelize_tool_batch()"""
        safe, serial = [], []
        for c in calls:
            if c.name in self._NEVER_PARALLEL:
                serial.append(c)
            else:
                safe.append(c)
        return safe, serial

    # ── Doom Loop 检测 ──
    def detect_doom_loop(self, history: list[ToolCall]) -> bool:
        """对标 OpenCode processor.ts:350——连续3次同工具同参数"""
        if len(history) < 3: return False
        last3 = history[-3:]
        return all(c.tool == last3[0].tool and c.args == last3[0].args for c in last3)

@dataclass
class ToolEntry:
    """对标 Hermes ToolEntry——工具的完整元数据。"""
    name: str
    toolset: str
    schema: dict           # JSON Schema (LLM 可见)
    handler: Callable      # 实际执行函数
    check_fn: Callable | None = None  # 运行时可用性检查
    concurrency: str = "safe"  # "safe" | "serial" | "never_parallel"
    max_result_chars: int = 10000  # >10K → 截断（AC6b）
```

### 4.2 6 核心工具（AC1）

```python
# src/orbit/tools/filesystem.py
@registry.register(
    name="read_file", toolset="filesystem",
    schema={"type":"function","function":{"name":"read_file","parameters":{...}}},
    handler=read_file, concurrency="safe",
)
async def read_file(path: str, offset: int = 0, limit: int = 200) -> str: ...

@registry.register(name="write_file", toolset="filesystem", schema={...},
                   handler=write_file, concurrency="serial")
async def write_file(path: str, content: str) -> None: ...

@registry.register(name="edit_file", toolset="filesystem", schema={...},
                   handler=edit_file, concurrency="serial")
async def edit_file(path: str, old_string: str, new_string: str) -> None: ...

# src/orbit/tools/shell.py
@registry.register(name="exec_command", toolset="shell", schema={...},
                   handler=exec_command, concurrency="never_parallel")
async def exec_command(cmd: str, cwd: str = ".", timeout: int = 30) -> ExecResult: ...

# src/orbit/tools/search.py
@registry.register(name="grep", toolset="search", schema={...},
                   handler=grep, concurrency="safe")
async def grep(pattern: str, path: str = ".") -> list[Match]: ...

@registry.register(name="glob", toolset="search", schema={...},
                   handler=glob_files, concurrency="safe")
async def glob_files(pattern: str, path: str = ".") -> list[str]: ...
```

### 4.3 ReActAgent 基类（AC5）

```python
# src/orbit/agents/react_agent.py
class ReActAgent(BaseAgent):
    """对标 OpenCode runLoop() + Claude Code while loop。"""
    MAX_TURNS = 20
    ITERATION_BUDGET = 90  # 对标 Hermes max_iterations

    def __init__(self, llm=None, graph=None, sandbox=None, tools=None):
        super().__init__(llm, graph, sandbox)
        self.tools = tools or ToolRegistry()  # 注入工具注册表
        self._tool_history: list[ToolCall] = []  # Doom Loop 检测用
        self._budget = IterationBudget(self.ITERATION_BUDGET)  # 对标 Hermes

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """ReAct 循环主入口——每步实时推送到事件总线（非黑盒）。"""
        # 1. 构建 system prompt（AC6）
        system = PromptBuilder().build(self.role, input_data.context)

        # 2. 初始化消息历史
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": input_data.task},
        ]
        tools_schema = self.tools.get_schemas()
        reasoning_chain: list[dict] = []  # L0 推理链——用户可见

        # 3. ReAct 循环（对标 OpenCode runLoop）
        for turn in range(self.MAX_TURNS):
            # 3a. LLM 思考
            response = await self.llm.generate(messages, tools_schema)

            # 3a+. 推送推理步骤到驾驶舱（用户实时可见）
            await self._emit("turn_start", {"turn": turn, "agent": self.role.value})

            # 3b. 判断退出
            if response.stop_reason == "end_turn":
                reasoning_chain.append({
                    "turn": turn, "action": "finish",
                    "reasoning": response.reasoning or response.content[:500],
                })
                await self._emit("turn_end", {"turn": turn, "action": "complete"})
                return AgentOutput(
                    status="ok",
                    result={**self._parse_result(response),
                            "reasoning_chain": reasoning_chain,  # L0 推理链
                            "turns": turn + 1,
                            "tool_calls": len(self._tool_history)},
                )

            # 3c. 执行工具
            if response.stop_reason == "tool_calls":
                for tc in response.tool_calls:
                    # 3d. Doom Loop 检测（AC4）
                    if self.tools.detect_doom_loop(self._tool_history + [tc]):
                        raise DoomLoopError(f"检测到死循环: {tc.name} × 3")

                    # 3e. 推送工具调用事件（用户实时可见）
                    await self._emit("tool_call_start", {
                        "tool": tc.name, "args": tc.args, "turn": turn,
                    })

                    # 3f. 执行工具 + 截断输出（AC6b）
                    result = await self.tools.dispatch(tc.name, tc.args)
                    truncated = self._truncate_output(result)
                    reasoning_chain.append({
                        "turn": turn, "action": tc.name,
                        "args": tc.args, "result_preview": truncated[:200],
                    })
                    messages.append({"role": "tool", "content": truncated})

                    # 3g. 推送工具结果
                    await self._emit("tool_call_end", {
                        "tool": tc.name, "result_size": len(result),
                        "truncated": len(result) > 10000,
                    })

                    self._tool_history.append(tc)
                    self._budget.consume()

                continue  # ← 回到 3a

        return AgentOutput(status="error", error=f"超过 {self.MAX_TURNS} 轮")

    async def _emit(self, event_type: str, data: dict) -> None:
        """推送事件到 EventBus——对标 OpenCode fullStream events。"""
        if hasattr(self, '_event_bus') and self._event_bus:
            await self._event_bus.publish(f"agent.{event_type}", data)
```

### 4.4 PromptBuilder——三层拼接（AC6）

```python
# src/orbit/prompt/builder.py
class PromptBuilder:
    """对标 Hermes prompt_builder.py + Claude Code 7-layer 缓存边界。

    三层（stable 可缓存 / context 半缓存 / volatile 不缓存）：
    """
    def build(self, role: AgentRole, context: dict) -> str:
        sections = []

        # ── stable 层（可缓存）──
        sections.append(f"你是 Orbit 协作网络中的 {role.value} Agent。")
        sections.append(self._tools_section(role))      # 可用工具列表 + 使用指南
        sections.append(self._rules_section())           # 强制规则 + 禁止项
        sections.append(self._output_format_section())   # 输出格式要求

        # ── context 层（半缓存）──
        sections.append(self._project_section(context))  # 项目信息 + 技术栈

        # ── volatile 层（不缓存）──
        sections.append(self._task_section(context))     # 当前任务 + 约束
        sections.append(self._budget_section())           # token 预算压力

        return "\n\n".join(sections)
```

### 4.5 Shell 白名单（AC6a）

```python
# src/orbit/tools/shell.py
SHELL_WHITELIST = {
    "git": ["status","diff","add","commit","log","branch","checkout","push","pull"],
    "pytest": ["*"],      # 全部子命令允许
    "python": ["-m","-c"],
    "pnpm": ["install","build","test","lint"],
    "uv": ["add","run","lock"],
    "ls": ["*"], "cat": ["*"], "grep": ["*"], "find": ["*"],
    "echo": ["*"], "mkdir": ["*"], "cp": ["*"], "mv": ["*"],
}

def validate_command(cmd: str) -> bool:
    """对标 Claude Code 23 Bash validators——白名单 + 危险模式检测。"""
    parts = shlex.split(cmd)
    if not parts: return False
    base = parts[0]
    if base not in SHELL_WHITELIST:
        raise ShellBlockedError(f"命令 '{base}' 不在白名单中")
    # 禁止危险组合: rm -rf /, chmod 777, curl | sh
    if "rm" in cmd and ("-rf" in cmd or "-r" in cmd): raise ShellBlockedError("禁止递归删除")
    if "|" in cmd and ("sh" in cmd or "bash" in cmd): raise ShellBlockedError("禁止管道到shell")
    return True
```

### 4.6 Factory 改造——DeveloperAgent 继承 ReActAgent（AC5）

```python
# src/orbit/agents/factory.py 修改
class DeveloperAgent(ReActAgent):  # ← 从 BaseAgent 改为 ReActAgent
    role = AgentRole.DEVELOPER

    # execute() 继承自 ReActAgent——自动获得 think→act→observe 循环
    # 只需提供 system_prompt()

class ArchitectAgent(ReActAgent):
    role = AgentRole.ARCHITECT

class ReviewerAgent(ReActAgent):
    role = AgentRole.REVIEWER
    MAX_TURNS = 10  # 审查不需要太多轮

class QAAgent(ReActAgent):
    role = AgentRole.QA

# ConfigAgent, ClarifierAgent 保持 BaseAgent——不需要工具
```

---

## 5. 数据流

```
用户提交 PRD
  → Scheduler._agent_cycle(CODING)
    → DeveloperAgent.execute(input_data)
      ├─ PromptBuilder.build("developer", context)
      │   ├─ stable: 角色 + 6工具 + 规则
      │   ├─ context: 项目 + 技术栈
      │   └─ volatile: 任务 + 预算
      │
      └─ ReAct 循环（每步推送到驾驶舱——用户实时可见）:
          Round 1: LLM→"需要读main.py" → [emit: turn_start+tool_call_start]
                   → read_file("src/main.py") → [emit: tool_call_end]
                   → 内容反馈给 LLM → [emit: turn_end]
          Round 2: LLM→"需要改第42行" → [emit: tool_call_start]
                   → edit_file("src/main.py", ...) → [emit: tool_call_end]
          Round 3: LLM→"跑测试验证" → [emit: tool_call_start]
                   → exec_command("pytest -q") → [emit: tool_call_end]
          Round 4: LLM→"完成" → [emit: turn_end(complete)]
                   → AgentOutput {result, reasoning_chain, turns:4, tool_calls:3}
      │
      └─ 驾驶舱实时显示:
           Agent 思考中... → 调用 read_file → ✓ 384行
           → 调用 edit_file → ✓ 已修改
           → 调用 exec_command → ✓ 28 passed
           → 任务完成 (4 轮, 3 次工具调用)
```

**用户看到的不是黑盒**——每一步工具调用、每次 LLM 思考、推理链，都通过 EventBus 实时推送到驾驶舱。对标 OpenCode fullStream events。

---

## 6. 与 PRD 对照

| AC | 实现 | 文件 |
|----|------|------|
| AC1 | 6 工具 + AST 自注册 | `tools/registry.py` + `tools/*.py` |
| AC2 | ToolEntry 三层解耦 | `tools/registry.py` ToolEntry dataclass |
| AC3 | `_should_parallelize()` | `tools/registry.py` 三类判定 |
| AC4 | `detect_doom_loop()` | `tools/registry.py` |
| AC5 | ReActAgent.execute() 循环 | `agents/react_agent.py` |
| AC6 | PromptBuilder.build() | `prompt/builder.py` |
| AC6a | `validate_command()` 白名单 | `tools/shell.py` |
| AC6b | `_truncate_output()` | `agents/react_agent.py` |

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| LLM 不理解 JSON Schema 格式的 tool call | 先用 OpenAI function calling 格式（兼容性最好），后续加 Anthropic native |
| ReAct 循环导致 LLM 调用次数暴增 | iteration_budget 硬上限 90 + MAX_TURNS 20 |
| Shell 白名单限制太严影响开发效率 | 白名单可持续扩展 + 日志记录被拒命令供审查 |
| AST 自注册在大型项目可能慢 | 只在 `discover()` 调用时扫描一次，结果缓存 |
