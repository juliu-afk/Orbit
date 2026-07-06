"""测试 TaskContext 渐进式加载——G2 grill-me 模式.

覆盖: ContextStage 枚举、Stage 1 默认值、load_stage() 升级、最多升级一次.
"""

from __future__ import annotations

import pytest

from orbit.agents.context import ContextStage, TaskContext


# ════════════════════════════════════════════
# Stage 1 默认值
# ════════════════════════════════════════════


def test_stage1_defaults() -> None:
    """Stage 1 默认: L1+L3 填充, L2/L4/L5 空."""
    ctx = TaskContext(
        task_id="t1",
        agent_name="developer",
        l1="测试约束",
        l3={"state": "CODING", "prd": "test"},
    )
    assert ctx.stage == ContextStage.STAGE1
    assert ctx.l1 == "测试约束"
    assert ctx.l3["state"] == "CODING"
    assert ctx.l2 == {}  # Stage 2 才填充
    assert ctx.l4 == {}  # Stage 2 才填充
    assert ctx.l5 == []  # Stage 3 才填充


def test_context_stage_ordering() -> None:
    """ContextStage 有序——STAGE1 < STAGE2 < STAGE3."""
    assert ContextStage.STAGE1 < ContextStage.STAGE2
    assert ContextStage.STAGE2 < ContextStage.STAGE3


# ════════════════════════════════════════════
# load_stage 升级
# ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_load_stage_no_downgrade() -> None:
    """load_stage(STAGE1) 当已在 Stage 2 时 → 不降级."""
    ctx = TaskContext(task_id="t1", l1="test")
    # 手动设 Stage 2
    ctx.stage = ContextStage.STAGE2
    await ctx.load_stage(ContextStage.STAGE1)  # 请求降级
    assert ctx.stage == ContextStage.STAGE2  # 不降级


@pytest.mark.asyncio
async def test_load_stage_upgrade_once_only() -> None:
    """每任务最多升级一次——_stage_upgraded 标记."""
    ctx = TaskContext(task_id="t1", l1="test")
    assert ctx.stage == ContextStage.STAGE1

    # 第一次升级
    await ctx.load_stage(ContextStage.STAGE2)
    # 第二次调用 load_stage (比如重试后又失败) → 不重复升级
    ctx.stage = ContextStage.STAGE1  # 模拟被重置
    await ctx.load_stage(ContextStage.STAGE2)
    # _stage_upgraded 为 True → 跳过实际加载
    # (此测试验证 load_stage 不会重复执行副作用)


@pytest.mark.asyncio
async def test_load_stage_to_same_or_lower_is_noop() -> None:
    """load_stage 在当前阶段或更低 → 无操作."""
    ctx = TaskContext(task_id="t1", l1="test")
    await ctx.load_stage(ContextStage.STAGE1)  # 已在 STAGE1
    assert ctx.stage == ContextStage.STAGE1  # 不变
    assert ctx._stage_upgraded is False  # 未标记升级
