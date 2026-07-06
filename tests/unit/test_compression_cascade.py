"""CascadePruner 单元测试——覆盖 Stage 1-3 边界分支。"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from orbit.compression.cascade import CascadePruner
from orbit.compression.models import CompressionAction


def test_init():
    p = CascadePruner()
    assert p is not None


@pytest.mark.asyncio
async def test_prune_budget_none():
    """budget=None → 直接返回原消息（no-op）。"""
    p = CascadePruner()
    messages = [{"role": "user", "content": "hello"}]
    result, stages, removed = await p.prune_if_needed(messages, None, None)
    assert result == messages
    assert stages == []
    assert removed == 0


@pytest.mark.asyncio
async def test_prune_not_force():
    """budget 未到 FORCE 阈值 → 直接返回。"""
    p = CascadePruner()
    budget = Mock()
    budget.check_threshold.return_value = CompressionAction.WARN  # 不是 FORCE
    messages = [{"role": "user", "content": "hello"}]
    result, stages, removed = await p.prune_if_needed(messages, None, budget)
    assert result == messages


def test_stage1_strip_consumed_non_string_content():
    """tool 消息 content 非字符串（如 list/dict）→ 保留（lines 142-143）。"""
    p = CascadePruner()
    messages = [
        {"role": "tool", "tool_call_id": "t1", "content": ["file1.py", "file2.py"]},
    ]
    result = p._stage1_strip_consumed(messages, None)
    assert len(result) == 1  # 非字符串→保留


def test_stage1_strip_consumed_small_output():
    """小型 tool 输出（< threshold）→ 保留。"""
    p = CascadePruner(large_output_threshold=99999)
    messages = [
        {"role": "tool", "tool_call_id": "t1", "content": "short output"},
    ]
    result = p._stage1_strip_consumed(messages, None)
    assert len(result) == 1  # 太小→保留


def test_stage1_strip_consumed_error_output():
    """错误输出 → 始终保留。"""
    p = CascadePruner()
    # 模拟错误信息（含有 error/traceback 关键词）
    error_content = "Error: something went wrong\nTraceback (most recent call last):\n..."
    messages = [
        {"role": "tool", "tool_call_id": "t1", "content": error_content},
    ]
    result = p._stage1_strip_consumed(messages, None)
    assert len(result) == 1  # 错误→保留


def test_stage2_remove_effectless_empty():
    """空消息列表 → 返回空。"""
    p = CascadePruner()
    result = p._stage2_remove_effectless([], None)
    assert result == []


def test_stage2_remove_effectless_system_only():
    """只有 system 消息 → 保留。"""
    p = CascadePruner()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]
    result = p._stage2_remove_effectless(messages, None)
    assert len(result) == 1


def test_stage2_with_tool_calls():
    """assistant 消息含 tool_calls → consecutive_ineffectual 重置。"""
    p = CascadePruner()
    messages = [
        {"role": "assistant", "content": "thinking...", "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "result"},
    ]
    result = p._stage2_remove_effectless(messages, None)
    # 含 tool_calls → 保留所有
    assert len(result) >= 2


def test_stage3_no_assistant_messages():
    """消息列表无 assistant → 返回原消息（line 261）。"""
    p = CascadePruner()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "tool", "tool_call_id": "t1", "content": "result"},
    ]
    result = p._stage3_structured_summary(messages, None)
    assert result == messages


def test_stage3_few_messages():
    """头部消息 ≤2 → 不值得压缩 → 返回原消息。"""
    p = CascadePruner()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    result = p._stage3_structured_summary(messages, None)
    # head 只有 system → ≤2 → 返回原消息
    assert result == messages


@pytest.mark.asyncio
async def test_prune_cascade_force_then_done():
    """第1次 FORCE → 运行 Stage 1 → 第2次非 FORCE → 早返回（line 99）。"""
    p = CascadePruner()
    budget = Mock()
    budget.check_threshold.side_effect = [
        CompressionAction.FORCE,
        CompressionAction.WARN,  # Stage 1 后不再 FORCE
    ]
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    result, stages, removed = await p.prune_if_needed(messages, None, budget)
    assert "strip_consumed" in stages
    assert len(stages) == 1  # 只到 Stage 1


@pytest.mark.asyncio
async def test_prune_cascade_stage3_then_done():
    """Stage 1→2→3 全部运行 → 第3次后非 FORCE → 早返回（line 111）。"""
    p = CascadePruner()
    budget = Mock()
    budget.check_threshold.side_effect = [
        CompressionAction.FORCE,  # 触发 Stage 1
        CompressionAction.FORCE,  # 触发 Stage 2
        CompressionAction.FORCE,  # 触发 Stage 3
        CompressionAction.WARN,  # Stage 3 后不再 FORCE
    ]
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "ok"},
    ]
    result, stages, removed = await p.prune_if_needed(messages, None, budget)
    assert "strip_consumed" in stages
    assert "remove_ineffectual" in stages
    assert "structured_summary" in stages
    assert "need_llm_summary" not in stages  # 在第3次后早返回
