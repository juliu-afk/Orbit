# ADR：业界追赶——架构决策记录（Phase 1-3）

> 日期: 2026-06-27 | 基于 5 框架源码研究 | 7 条决策

---

## ADR-001：工具注册——AST 自发现 vs 手动 manifest

### 决策

**AST 自发现（对标 Hermes）。**

### 理由

- Hermes `discover_builtin_tools()` 用 `ast.parse()` 扫描 `tools/*.py`，发现 `registry.register()` 即自动导入。零维护成本。
- 手动 manifest（列表 import）每次加工具要改 2 个文件，容易遗漏。
- OpenClaw 用 9 层 config merge，Orbit 不需要那么复杂——先 AST 自发现 + check_fn 过滤。

### 实现

```python
# src/orbit/tools/registry.py
class ToolRegistry:
    @classmethod
    def discover(cls, paths: list[str]) -> None:
        for path in paths:
            for f in Path(path).rglob("*.py"):
                tree = ast.parse(f.read_text())
                if cls._has_register_call(tree):
                    importlib.import_module(f"tools.{f.stem}")
```

---

## ADR-002：ReAct 循环——同步 vs 流式

### 决策

**先同步循环，P1 再加流式。**

### 理由

- Claude Code 的循环是同步的（while + await），OpenCode 是流式的（for event in fullStream）
- 流式中断更复杂（需要 AbortController + partial result 处理）
- P0 目标是让 Agent 能干活，同步循环足够
- 流式放在 P1——对标 OpenCode runLoop 事件驱动

---

## ADR-003：Prompt 构建——内联 vs PromptBuilder 类

### 决策

**PromptBuilder 类（对标 Hermes prompt_builder.py）。**

### 理由

- 当前 `system_prompt()` 只返回 3 行字符串，无法注入工具列表/规则/上下文
- PromptBuilder 支持三层：stable（缓存） + context（半缓存） + volatile（不缓存）
- 对标 Claude Code 7 层缓存边界——Anthropic API 的 `cache_control` 标记 later in P1

---

## ADR-004：工具并发——ThreadPool vs asyncio

### 决策

**asyncio.gather（Python 原生）。**

### 理由

- Hermes 用 `ThreadPoolExecutor(max_workers=8)` 因为有些工具是同步的
- Orbit 的工具全是 `async def`（文件 I/O 用 aiofiles，Shell 用 asyncio.subprocess）
- `asyncio.gather` 零依赖，无需线程池
- 对标 Hermes 三类调度：`_NEVER_PARALLEL_TOOLS` / `_PARALLEL_SAFE_TOOLS` / `_PATH_SCOPED_TOOLS`

---

## ADR-005：Shell 工具——白名单 vs 沙箱 vs 全开放

### 决策

**P0: 命令白名单。P2: Docker 沙箱。**

### 理由

- Claude Code 有 23 Bash validators + AST-level shell parsing，Orbit P0 做不到
- 白名单模式：`git`, `pytest`, `python`, `pnpm`, `uv`, `ls`, `cat`, `grep`, `find`
- Orbit 已有 Docker 沙箱（`src/orbit/sandbox/`），P2 时接到 Shell 工具上
- OpenClaw 的 exec/process 替代 bash 方案可作为 P2 参考

---

## ADR-006：文件编辑——字符串替换 vs AST 编辑

### 决策

**字符串精确替换（对标 Claude Code Edit 工具）。**

### 理由

- Claude Code 的 Edit = `old_string → new_string`，简单可靠
- AST 编辑（Tree-sitter）精度高但实现复杂，P2 考虑
- Orbit 已有代码图谱（Tree-sitter），未来可做 AST 级 edit

---

## ADR-007：工具 Schema——JSON Schema vs Zod vs 自定义

### 决策

**JSON Schema（对标 Claude Code + Hermes）。**

### 理由

- OpenAI/Anthropic function calling 原生支持 JSON Schema
- Zod（OpenCode/MiMo）是 TypeScript 特化，Python 没有等价物
- Hermes 的 `registry.register(schema={...})` 直接传 dict，最简单
