"""Agent 测试自循环模块 —— 将测试从人类手动执行升级为 Agent 内建质量闭环。

五层内循环：意图理解 → 测试生成 → 代码生成(TDD) → 沙箱执行 → 反馈闭环。

全局钩子::
    from orbit import testing
    testing.setup(orchestrator)
    # Agent 生成代码后调用:
    await testing.run_on_code(code, module, goal_id)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.testing.orchestrator import TestOrchestrator

logger = logging.getLogger(__name__)

# 全局 orchestrator 实例——由 main.py 启动时注入
_orchestrator: TestOrchestrator | None = None


def setup(orchestrator: TestOrchestrator) -> None:
    """注入 orchestrator 实例——由应用启动时调用。

    应在 main.py 或 compose/orchestrator 初始化时调用。
    testing/ 模块所有入口依赖此钩子。
    """
    global _orchestrator
    _orchestrator = orchestrator
    logger.info("testing_orchestrator_ready")


async def run_on_code(
    code: str,
    module: str = "",
    goal_id: str = "",
    prd_text: str = "",
) -> dict | None:
    """Agent 代码生成后触发测试执行的全局入口。

    调用方（Agent/ComposeOrchestrator/CLI）无需了解 testing/ 内部——
    传代码 + 模块名即可，返回前端可消费的摘要卡片 JSON。

    Returns:
        dict | None: 摘要卡片 JSON（供聊天流展示），orchestrator 未注入时返回 None
    """
    if _orchestrator is None:
        logger.warning("testing_orchestrator_not_ready——跳过测试")
        return None
    return await _orchestrator.run(
        code=code,
        module=module,
        goal_id=goal_id,
        prd_text=prd_text,
    )
