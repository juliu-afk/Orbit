"""Agent 级 Subagent 生成工具——spawn_subagent。

WHY: 让 Agent 在 ReAct 循环中自主 spawn 子 Agent 并行工作。
- DeveloperAgent: 并行调研多个模块
- ReviewerAgent: 并行审查不同维度（安全/性能/正确性）
- QAAgent: 并行生成不同场景的测试用例

安全约束:
- 深度限制: 子 Agent 的 ROLE_TOOLS 不含 spawn_subagent → 不可递归
- 角色白名单: 只能 spawn architect/developer/reviewer/qa
- 并发上限: 全局 MAX_CONCURRENT=4 共享
- 超时: 默认 120s，父 Agent 可自定义
"""

from __future__ import annotations

import json as _json
from typing import Any

import structlog

from orbit.tools.registry import get_registry

logger = structlog.get_logger("orbit.tools.subagent")

# ── 模块级状态（由 main.py 注入） ─────────────────────────

_actor_spawn: Any = None  # ActorSpawn 实例——main.py 启动时注入

# 可 spawn 的子 Agent 角色白名单
# WHY: chatter/clarifier 是纯对话角色，不应作为子 Agent 执行编程任务
SPAWN_ALLOWED_ROLES = {"architect", "developer", "reviewer", "qa"}

# 默认超时（秒）
DEFAULT_TIMEOUT = 120


def set_actor_spawn(spawn: Any) -> None:
    """注入 ActorSpawn 实例——main.py 启动时调用。

    对标 filesystem.set_workspace_root() 模式。
    """
    global _actor_spawn
    _actor_spawn = spawn
    logger.info("subagent_actor_spawn_injected")


# ── Tool Handler ──────────────────────────────────────────


async def spawn_subagent(
    role: str = "developer",
    task: str = "",
    context: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """spawn_subagent 工具 handler——创建子 Agent 并等待结果。

    Args:
        role: 子 Agent 角色（architect/developer/reviewer/qa）
        task: 任务描述——必须具体明确
        context: 额外上下文（可选）——如相关代码片段、已验证结论等
        timeout: 超时秒数（默认 120s）

    Returns:
        JSON 字符串: {status, actor_id, output, turns, tool_calls, error}
    """
    # 1. 校验角色白名单
    if role not in SPAWN_ALLOWED_ROLES:
        return _json.dumps(
            {
                "status": "error",
                "error": (
                    f"role_not_allowed: '{role}'。"
                    f"允许的子 Agent 角色: {', '.join(sorted(SPAWN_ALLOWED_ROLES))}"
                ),
            },
            ensure_ascii=False,
        )

    # 2. 校验 actor_spawn 已初始化
    if _actor_spawn is None:
        return _json.dumps(
            {
                "status": "error",
                "error": "actor_spawn_not_configured——子 Agent 系统未初始化",
            },
            ensure_ascii=False,
        )

    # 3. 构建上下文
    ctx: dict[str, Any] = {}
    if context:
        ctx["parent_context"] = context

    # 4. 尝试 spawn 子 Agent
    try:
        deferred = await _actor_spawn.spawn(
            task=task,
            role=role,
            parent_task_id="",  # 工具层无父 task_id——ActorRegistry 的 actor_id 足够追踪
            context=ctx,
            background=False,
        )
    except RuntimeError as e:
        # 并发满——MAX_CONCURRENT=4
        return _json.dumps(
            {
                "status": "rejected",
                "reason": "concurrency_limit",
                "detail": str(e),
            },
            ensure_ascii=False,
        )

    # 5. 等待子 Agent 完成
    try:
        result = await deferred.result(timeout=timeout)
        logger.info(
            "subagent_completed",
            actor_id=deferred.actor_id,
            role=role,
            status=result.get("status", "unknown"),
        )
        return _json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.warning(
            "subagent_failed",
            actor_id=deferred.actor_id,
            role=role,
            error=str(e),
        )
        return _json.dumps(
            {
                "status": "error",
                "actor_id": deferred.actor_id,
                "error": str(e),
            },
            ensure_ascii=False,
        )


# ── AST 自注册 ──────────────────────────────────────────
# 对标 filesystem.py: 文件底部 registry.register_tool() 即自动发现

registry = get_registry()
registry.register_tool(
    name="spawn_subagent",
    toolset="subagent",
    schema={
        "type": "function",
        "function": {
            "name": "spawn_subagent",
            "description": (
                "创建子Agent并行执行任务。用于：并行调研多个文件/模块、"
                "并行审查代码的不同维度（安全性/性能/正确性）、"
                "并行生成不同场景的测试用例。"
                "子Agent角色限制为architect/developer/reviewer/qa，最大并发4。"
                "子Agent不可再spawn孙子Agent。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": ["architect", "developer", "reviewer", "qa"],
                        "description": "子Agent角色——architect(架构分析)/developer(编码)/reviewer(审查)/qa(测试)",
                    },
                    "task": {
                        "type": "string",
                        "description": "子Agent任务描述——必须具体明确，包含验收标准。例如：'分析 src/auth.py 的安全漏洞，输出漏洞列表和修复建议'",
                    },
                    "context": {
                        "type": "string",
                        "description": "额外上下文（可选）——如相关代码片段、已验证的结论、设计文档摘要等。用于确保子Agent不重复父Agent已确认的内容。",
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 120,
                        "description": "超时秒数（默认120s）。复杂任务建议设180s。",
                    },
                },
                "required": ["role", "task"],
            },
        },
    },
    handler=spawn_subagent,
    concurrency="safe",  # 同批次多次 spawn 自动并行（由 _should_parallelize 处理）
)
