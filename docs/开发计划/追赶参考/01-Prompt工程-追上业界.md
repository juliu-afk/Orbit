# Prompt Engineering——追上业界方案

> 参考源: Claude Code (leaked), OpenCode, Hermes, MiMo Code

---

## 一、业界最佳实践

### Claude Code：7层模块化 + 缓存边界

Claude Code 的 System Prompt 由 7+ 层拼接，中间有**缓存边界**（约 92% prefix 复用率）：

```
[静态·可缓存]
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

**Orbit 可抄的**: 每个 Agent 的 `system_prompt()` 拆成 stable/context/volatile 三层，stable 层放 Anthropic 缓存边界前。

### OpenCode：环境注入 + AGENTS.md

```typescript
// session/prompt.ts
const systemPrompt = [
  currentDirectory,           // 当前工作目录
  systemEnvironment,          // OS/Shell 信息
  globalAgentsMd,             // ~/.config/opencode/AGENTS.md
  projectAgentsMd,            // 项目 AGENTS.md 或 CLAUDE.md
  skillDescriptions,          // 200+ 内置技能模板
  providerBasePrompt,         // 模型厂商默认 prompt
].join("\n");
```

**Orbit 可抄的**: TaskContext 已经收集了 L1-L5，缺的是把 `CLAUDE.md`/`AGENTS.md` 注入到 system prompt。

### Hermes：三层缓存 + prompt_builder

```python
# hermes/prompt_builder.py
class PromptBuilder:
    def build(self) -> list[dict]:
        stable = self._stable_section()     # 缓存——角色 + 规则 + 工具列表
        context = self._context_section()   # 半缓存——会话目标 + 约束
        volatile = self._volatile_section() # 不缓存——预算警告 + 压力提示
        return [{"role": "system", "content": stable + context + volatile}]
```

**Orbit 可抄的**: Hermes 的三层结构和 Anthropic 缓存标记机制。

### MiMo Code：角色 + 技能 + 记忆注入

每轮对话前动态拼接：
```
System: 你是 {role} Agent。当前项目 {project}。可用技能 {skills}。
Memory: {MEMORY.md 摘要}  ← checkpoint-writer 维护
Task:   {当前任务 + 约束 + 历史进度}
```

---

## 二、Orbit 当前状态

```python
# 每个 Agent 的 system_prompt() —— 只有 3 行
def system_prompt(self) -> str:
    return (
        f"你是 V14.1 多智能体协作网络中的 {self.role.value} Agent。"
        "在协作契约约束下工作，输出必须通过 L1-L8 验证。"
        '返回 JSON 格式：{"status": "ok", "result": {...}}'
    )
```

**问题**：
- 没有工具使用指南（不知道有哪些工具、怎么用）
- 没有输出格式约束（JSON schema 不够精确）
- 没有禁止项（可能生成危险代码）
- 没有上下文注入（TaskContext L1-L5 没进 prompt）
- 没有缓存策略（每次都全量发送）

---

## 三、实施方案

### Phase 1：三层结构化（对标 Hermes·1天）

```python
class DeveloperAgent(BaseAgent):
    def system_prompt(self) -> dict:
        return {
            "stable": (  # 缓存——角色定义 + 规则 + 工具列表
                f"你是 Orbit 协作网络中的 DeveloperAgent (role={self.role.value})。\n"
                "## 可用工具\n"
                "- read_file(path) → str: 读取文件内容\n"
                "- write_file(path, content): 写入文件\n"
                "- edit_file(path, old, new): 精确替换\n"
                "- exec_command(cmd, cwd): 执行 Shell 命令\n"
                "- grep(pattern, path): 正则搜索代码\n"
                "- glob(pattern): 匹配文件路径\n"
                "## 规则\n"
                "- 必须先读代码再改，禁止猜测\n"
                "- 金额用 Decimal，禁止 float\n"
                "- 禁止 eval()/exec()/硬编码密钥\n"
                "- 输出 JSON: {\"status\": \"ok\", \"result\": {...}}"
            ),
            "context": (  # 半缓存——项目信息
                f"项目: {self.graph.project_name}\n"
                f"技术栈: {self._detect_stack()}\n"
                f"工作目录: {os.getcwd()}"
            ),
            "volatile": (  # 不缓存——当前任务
                f"任务ID: {self._current_task_id}\n"
                f"PRD 摘要: {self._prd_summary}\n"
                f"约束: {self._constraints}"
            ),
        }
```

### Phase 2：System Prompt 自动拼接（对标 OpenCode·2天）

```python
# src/orbit/prompt/builder.py
class PromptBuilder:
    def build(self, agent_role: str, task_ctx: TaskContext) -> str:
        sections = [
            self._identity(agent_role),          # 从 agent.prompt.stable
            self._tools_list(agent_role),         # 从 ToolRegistry
            self._rules(),                        # 从 CLAUDE.md/AGENTS.md
            self._task_context(task_ctx),          # L1-L5 注入
            self._budget_warning(task_ctx),        # Token 预算压力
        ]
        return "\n\n".join(sections)
```

### Phase 3：缓存标记（对标 Claude Code·1天）

```python
# 在 Anthropic 模型调用时加 cache_control
if provider == "anthropic":
    messages[0]["content"][-1]["cache_control"] = {"type": "ephemeral"}
```

---

## 四、参考源码位置

| 项目 | 关键文件 | 行数 |
|------|---------|------|
| Claude Code | `system_prompt.ts` (leaked) | ~800 |
| OpenCode | `session/prompt.ts:1400` | runLoop + prompt 拼接 |
| Hermes | `prompt_builder.py` | ~200 |
| MiMo Code | Fork from OpenCode + `memory/` dir | ~500 |
