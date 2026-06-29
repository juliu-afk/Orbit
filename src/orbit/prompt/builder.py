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

    def build(
        self,
        role: AgentRole,
        context: dict[str, Any] | None = None,
        tools_schema: list[dict] | None = None,
    ) -> str:
        """构建完整的 system prompt.

        Args:
            role: Agent 角色
            context: 任务上下文 (project, task, code_context, env 等)
            tools_schema: 可用工具列表 (供 LLM 选择)
        """
        ctx = context or {}
        sections: list[str] = []

        # ── stable 层 ──
        sections.append(self._build_stable(role))

        # ── context 层 ──
        sections.append(self._build_context(ctx))

        # ── volatile 层 ──
        sections.append(self._build_volatile(ctx))

        return "\n\n".join(sections)

    # ── 各层构建 ────────────────────────────────────────

    def _build_stable(self, role: AgentRole) -> str:
        """stable 层——角色 + 规则 + 输出格式."""
        parts = [
            ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS[AgentRole.DEVELOPER]),
            TOOLS_GUIDE_BLOCK,
            RULES_BLOCK,
        ]
        return "\n\n".join(parts)

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
