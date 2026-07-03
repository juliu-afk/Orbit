"""PromptBuilder——stable/context/volatile 三层拼接.

对标: Hermes prompt_builder.py 三层缓存
     + Claude Code 7-layer 缓存边界设计

WHY 三层: 不同层有不同缓存策略——
  stable  可全缓存 (角色+工具+规则，每次相同)
  context 半缓存 (项目信息+技术栈，同项目不变)
  volatile 不缓存 (当前任务+预算，每次不同)
"""

from __future__ import annotations

from typing import Any

from orbit.agents.base import AgentRole
from orbit.context.relevance import extract_relevant_context

# P2-1: 上下文裁剪参数——从模块常量读取，允许调用方覆盖
DEFAULT_MAX_FRAGMENTS = 5
DEFAULT_MAX_CONTEXT_CHARS = 5000

# ── Agent 角色描述（stable 层）─────────────────────────────
# WHY 在这里集中定义: 不在 agent 各自文件中散落，统一管理+

ROLE_DESCRIPTIONS: dict[AgentRole, str] = {
    AgentRole.ARCHITECT: (
        "你是 Orbit 多智能体协作网络中的 **架构师 Agent**。\n"
        "职责：系统设计、技术选型、模块划分、数据流设计。\n"
        "不直接写代码——设计方案供 Developer Agent 消费。"
    ),
    AgentRole.DEVELOPER: (
        "你是 Orbit 多智能体协作网络中的 **开发者 Agent**。\n"
        "职责：读取代码、编写代码、修改代码、运行测试——完整的开发闭环。\n"
        "你拥有文件读写、代码搜索、命令执行等工具，请充分利用它们完成任务。"
    ),
    AgentRole.REVIEWER: (
        "你是 Orbit 多智能体协作网络中的 **审查员 Agent**。\n"
        "职责：代码审查——发现缺陷、安全隐患、性能问题。\n"
        "阅读提交的代码变更，逐条列出问题，不要写新代码。"
    ),
    AgentRole.QA: (
        "你是 Orbit 多智能体协作网络中的 **QA 验证员 Agent**。\n"
        "职责：测试用例生成、验证代码正确性、覆盖率分析。\n"
        "为给定代码生成 pytest 测试，覆盖正常路径和异常情况。"
    ),
    AgentRole.CONFIG_MANAGER: (
        "你是 Orbit 多智能体协作网络中的 **配置管理员 Agent**。\n"
        "职责：环境配置管理、配置漂移检测、配置文件维护。\n"
        "确保所有环境的配置一致性，检测并报告配置偏差。"
    ),
    AgentRole.CLARIFIER: (
        "你是 Orbit 多智能体协作网络中的 **需求澄清 Agent**。\n"
        "职责：理解用户自然语言需求，拆解为结构化任务。\n"
        "不写代码——输出结构化的需求文档供其他 Agent 消费。"
    ),
    AgentRole.DREAM: (  # Phase 2
        "你是 Orbit 多智能体协作网络中的 **自进化 Agent**。\n"
        "职责：定期扫描会话历史和记忆文件，合并去重经验教训。\n"
        "通过 /dream 命令触发，输出精简的 MEMORY.md。"
    ),
}


# ── 强制规则（stable 层）───────────────────────────────────

RULES_BLOCK = """## 强制规则

1. **金额一律 Decimal，禁止 float/double**——精确到分。
2. **禁止命令注入、SQL 注入、eval()、动态代码执行**。
3. **密钥/密码/Token 一律从环境变量读取**，禁止硬编码。
4. **新增依赖必须先确认**——不要为一个小功能引入一个包。
5. **写注释**——业务逻辑、财务计算、会计规则必须注释 WHY。
6. **路径用正斜杠 `/`**——跨平台兼容。
7. **编辑已有文件优先于新建**——三个相似行好过一个过早抽象。
8. **不添加未要求的功能、抽象、错误处理、兼容层**。
9. **简洁优先**——用最少代码行数实现功能但保持可读性。
   - 优先复用标准库和已有函数，不要自己重复造轮子
   - 写完检查：有能删掉的行吗？有能合并的变量吗？
   - 如果单个文件超过 200 行，重新审视——是不是做了太多事？
   - P2-5: 本规则为新增代码的质量约束，与规则 1-8 无优先级冲突——
     规则 5（写注释）和规则 8（不添加未要求功能）优先于代码行数目标

## 输出格式

- 代码块使用标准 markdown 格式：```python ... ```
- 修改文件后输出改动的文件列表和理由
- 测试结果输出通过/失败计数
"""


# ── 工具使用指南（stable 层）────────────────────────────────

TOOLS_GUIDE_BLOCK = """## 可用工具

你拥有以下工具来完成任务：

| 工具 | 用途 | 并发 |
|------|------|------|
| `read_file` | 读取文件内容（带行号） | 可并发 |
| `write_file` | 创建或覆盖文件 | 串行 |
| `edit_file` | 精确字符串替换 | 串行 |
| `exec_command` | 执行 Shell 命令（白名单） | 必须串行 |
| `grep` | 内容搜索 | 可并发 |
| `glob` | 文件模式匹配 | 可并发 |

**使用原则**：
- 先用 `grep` / `glob` 定位，再用 `read_file` 读取，最后 `edit_file` 修改
- 修改完代码后运行 `exec_command` 验证（pytest、python -m py_compile 等）
- 不要连续 3 次用同样的工具和参数——会被检测为死循环
- `exec_command` 有白名单限制：git, pytest, python, pnpm, npm, uv, ls, cat 等
"""


class PromptBuilder:
    """三层 Prompt 构建器.

    stable   = 角色定义 + 工具列表 + 强制规则 + 输出格式 (可缓存)
    context  = 项目信息 + 技术栈 + 当前环境 (半缓存，同项目复用)
    volatile = 当前任务 + 约束 + token 预算 (不缓存，每次不同)
    """

    # Anthropic cache_control 断点——stable+context 可缓存，volatile 不可
    # WHY: stable/context 在单次会话中不变，标记为 ephemeral 让 API 缓存
    # 对标 Claude Code 的 SYSTEM_PROMPT_DYNAMIC_BOUNDARY
    ANTHROPIC_CACHE_BOUNDARY = True

    def build(
        self,
        role: AgentRole,
        context: dict[str, Any] | None = None,
        tools_schema: list[dict] | None = None,
    ) -> str:
        """构建完整 system prompt（纯文本，向后兼容）."""
        ctx = context or {}
        sections: list[str] = []

        sections.append(self._build_stable(role, tools_schema))
        sections.append(self._build_context(ctx))
        sections.append(self._build_volatile(ctx))

        return "\n\n".join(sections)

    def build_for_anthropic(
        self,
        role: AgentRole,
        context: dict[str, Any] | None = None,
        tools_schema: list[dict] | None = None,
    ) -> list[dict]:
        """构建带 cache_control 断点的结构化 system prompt.

        WHY 独立方法: 返回 Anthropic content blocks 格式，
        stable+context 块末尾标记 cache_control，volatile 不标记。
        对标 Claude Code SYSTEM_PROMPT_DYNAMIC_BOUNDARY。
        """
        ctx = context or {}

        stable_text = self._build_stable(role, tools_schema)
        context_text = self._build_context(ctx)
        volatile_text = self._build_volatile(ctx)

        cached_block = stable_text + "\n\n" + context_text

        return [
            {
                "type": "text",
                "text": cached_block,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": volatile_text,
            },
        ]

    # ── 各层构建 ────────────────────────────────────────

    def _build_stable(self, role: AgentRole, tools_schema: list[dict] | None = None) -> str:
        """stable 层——角色 + 工具列表（按角色裁剪） + 规则 + 输出格式."""
        parts = [
            ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS[AgentRole.DEVELOPER]),
            self._build_tools_guide(role, tools_schema),
            self._build_mcp_guide(tools_schema),
            RULES_BLOCK,
        ]
        return "\n\n".join(parts)

    @staticmethod
    def _build_mcp_guide(tools_schema: list[dict] | None) -> str:
        """当存在 Serena MCP 工具时注入使用指南。

        WHY: Agent 默认不知道 MCP 工具的存在和用法——需要显式教会。
        """
        if not tools_schema:
            return ""
        mcp_tools = [
            s.get("function", {}).get("name", "")
            for s in tools_schema
            if s.get("function", {}).get("name", "").startswith("serena/")
        ]
        if not mcp_tools:
            return ""
        return """## Serena 语义代码工具（MCP）

你拥有 **Serena**——LSP 驱动的语义代码导航工具。**优先使用 Serena 而非 grep/read_file 做代码定位：**

| 任务 | ❌ 旧方式 | ✅ 用 Serena |
|------|----------|-------------|
| 定位函数/类定义 | `grep` 猜位置 | `{prefix}/find_symbol` 精确到行 |
| 查调用者/引用 | `grep` 搜函数名 | `{prefix}/find_referencing_symbols` 100% 准确 |
| 读文件结构 | `read_file` 整文件（15K tokens） | `{prefix}/get_symbols_overview` ~300 tokens |
| 跨文件重命名 | 手工 `edit_file` 逐个改 | `{prefix}/rename_symbol` 原子操作 |
| 替换函数体 | `edit_file` 字符串匹配（脆弱） | `{prefix}/replace_symbol_body` 手术级 |

**原则**：先 `get_symbols_overview` → `find_symbol` → 再动代码。
不要读完整个文件——用 overview 定位，用 find_symbol 精确读取。""".replace("{prefix}", "serena")

    @staticmethod
    def _build_tools_guide(role: AgentRole, tools_schema: list[dict] | None) -> str:
        """按角色生成工具使用指南——只列出该角色可用的工具.

        WHY 按角色裁剪: Clarifier 不应该看到 exec_command，
        Reviewer 不需要 write_file——减少 prompt 噪音 + 缩小攻击面。
        """
        if tools_schema is None:
            return TOOLS_GUIDE_BLOCK  # 未传 schema → 显示默认全部
        if not tools_schema:
            # 空列表 = 角色无工具（如 Clarifier）→ 不显示工具段
            return "## 可用工具\n\n当前角色无可用工具。"

        names = [
            s.get("function", {}).get("name", "")
            for s in tools_schema
            if s.get("function", {}).get("name")
        ]
        if not names:
            return TOOLS_GUIDE_BLOCK

        # 并发安全标记——与 ToolRegistry 常量保持一致
        SERIAL_TOOLS = {"exec_command", "edit_file"}
        SAFE_TOOLS = {"read_file", "grep", "glob", "write_file"}

        lines = ["## 可用工具", "", f"当前角色 {role.value} 可用工具：", ""]
        lines.append("| 工具 | 并发 |")
        lines.append("|------|------|")
        for name in names:
            if name in SERIAL_TOOLS:
                lines.append(f"| `{name}` | 串行 |")
            elif name in SAFE_TOOLS:
                lines.append(f"| `{name}` | 可并发 |")
            else:
                lines.append(f"| `{name}` | — |")

        lines.append("")
        lines.append(
            "**使用原则**：先 `grep`/`glob` 定位 → `read_file` 读取 → `edit_file` 修改。"
            " 不要连续 3 次用同样的工具和参数——会被检测为死循环。"
        )
        return "\n".join(lines)

    def _build_context(self, ctx: dict[str, Any]) -> str:
        """context 层——项目信息 + 技术栈."""
        project = ctx.get("project", "")
        tech_stack = ctx.get("tech_stack", "")
        code_context = ctx.get("code_context", "")
        env_info = ctx.get("env", {})

        parts = ["## 项目上下文"]

        if project:
            parts.append(f"**项目**: {project}")

        if tech_stack:
            parts.append(f"**技术栈**: {tech_stack}")

        if code_context:
            # 业务层减熵 P0: 用任务关键词提取最相关的代码片段
            task_keywords = ctx.get("keywords", [])
            if task_keywords:
                truncated = extract_relevant_context(
                    code_context,
                    task_keywords,
                    max_fragments=DEFAULT_MAX_FRAGMENTS,
                    max_chars=DEFAULT_MAX_CONTEXT_CHARS,
                )
            else:
                # 无关键词 → 降级为全文截断
                truncated = (
                    code_context[:5000] + "\n... (截断)"
                    if len(code_context) > 5000
                    else code_context
                )
            parts.append(f"\n已有代码上下文：\n```\n{truncated}\n```")

        if env_info:
            safe_env = {
                k: v
                for k, v in env_info.items()
                if not any(s in k.lower() for s in ("key", "secret", "token", "password"))
            }
            if safe_env:
                parts.append(f"\n环境信息：{safe_env}")

        # L2.5: 项目说明书注入——.orbit/brief.md + boundaries + 目录级 context.md
        # WHY 在记忆之前注入: 项目说明书是比记忆更可靠的事实来源，
        # Agent 应先读说明书再参考历史经验。
        brief = ctx.get("brief", "")
        if brief:
            # 截断到 2000 chars——说明书是背景信息，不应占据太多 token
            brief_truncated = brief[:2000] + "\n... (截断)" if len(brief) > 2000 else brief
            parts.append(f"\n## 项目说明书\n{brief_truncated}")

        boundaries = ctx.get("boundaries", "")
        if boundaries:
            # 只注入 rules 列表，跳过 YAML 头
            boundaries_short = boundaries[:1000]
            parts.append(f"\n## 边界规则\n{boundaries_short}")

        # 目录级 CONTEXT.md 层级——从目标文件向上收集
        context_md = ctx.get("context_md")
        if context_md and isinstance(context_md, list):
            ctx_lines = ["\n## 目录上下文（最近优先）"]
            # WHY 600 chars: 300 过少（API 路由层一两行注释不够），
            # 600 可容纳 4-6 行实质性说明且保持 token 预算可控（~200 tokens/层）。
            for dir_path, content in context_md[-3:]:  # 最多 3 个层级
                dir_name = dir_path.split("/")[-1] if "/" in dir_path else dir_path.split("\\")[-1]
                ctx_lines.append(f"### {dir_name}/\n{content[:600]}")
            parts.append("\n".join(ctx_lines))

        # 基础代码包——按 LLM 决策注入
        base_pkg = ctx.get("base_package")
        if base_pkg and isinstance(base_pkg, dict) and base_pkg.get("decision") != "skip":
            pkg_info = f"决策: {base_pkg.get('decision')} | "
            pkg_info += f"包: {', '.join(base_pkg.get('package_ids', []))} | "
            pkg_info += f"理由: {base_pkg.get('reason', '')}"
            parts.append(f"\n## 基础代码包\n{pkg_info[:500]}")

        # Phase 2: 记忆注入——Agent 工作记忆 + 记忆检索结果
        working_memory = ctx.get("working_memory")
        if working_memory and hasattr(working_memory, "body") and working_memory.body:
            parts.append(f"\n## Agent 工作记忆\n```\n{working_memory.body[:2000]}\n```")

        memory_search_results = ctx.get("memory_search_results", [])
        if memory_search_results:
            mem_text = "\n".join(
                f"- [{r.path}] (score={r.score:.2f}) {r.snippet[:150]}"
                for r in memory_search_results[:5]
            )
            parts.append(f"\n## 记忆检索结果\n{mem_text}")

        if len(parts) == 1:
            return "## 项目上下文\n无特定项目上下文。通用开发环境。"

        return "\n".join(parts)

    def _build_volatile(self, ctx: dict[str, Any]) -> str:
        """volatile 层——当前任务 + 约束."""
        task = ctx.get("task", "")
        constraints = ctx.get("constraints", [])

        parts = ["## 当前任务"]

        if task:
            parts.append(task)

        if constraints:
            parts.append("\n约束条件：")
            for c in constraints:
                parts.append(f"- {c}")

        # token 预算提示（如果设置了）
        budget = ctx.get("token_budget", 0)
        if budget:
            parts.append(f"\nToken 预算: {budget} tokens")

        return "\n".join(parts)

    # ── 便捷方法 ────────────────────────────────────────

    def build_stable_only(self, role: AgentRole) -> str:
        """只构建 stable 层——供缓存命中时使用."""
        return self._build_stable(role)

    def build_system_and_user(
        self,
        role: AgentRole,
        task: str,
        context: dict[str, Any] | None = None,
        tools_schema: list[dict] | None = None,
    ) -> dict[str, str]:
        """构建 system prompt + 首条 user message.

        Returns:
            {"system": ..., "user": ...}
        """
        ctx = (context or {}) | {"task": task}
        return {
            "system": self.build(role, ctx, tools_schema),
            "user": task,
        }
