"""Task/状态机专用断言。

用于验证调度器状态转换、检查点保存、事件发布。
"""

from __future__ import annotations

from typing import Any


def assert_state_transition(
    history: list[str],
    from_state: str,
    to_state: str,
    msg: str = "",
) -> None:
    """验证状态转换在历史记录中存在。

    检查 from_state 和 to_state 在 history 中相邻出现。

    Args:
        history: 状态历史列表
        from_state: 期望的起始状态
        to_state: 期望的目标状态
        msg: 额外错误消息
    """
    for i in range(len(history) - 1):
        if history[i] == from_state and history[i + 1] == to_state:
            return

    detail = f"状态历史: {history}"
    if msg:
        detail = f"{msg}\n{detail}"
    raise AssertionError(f"未找到状态转换 {from_state} → {to_state}\n{detail}")


def assert_checkpoint_saved(
    checkpoints: list[dict[str, Any]],
    expected_state: str,
    msg: str = "",
) -> None:
    """验证检查点已保存且包含指定状态。

    Args:
        checkpoints: 检查点列表（每个 dict 含 'state' 键）
        expected_state: 期望的状态
        msg: 额外错误消息
    """
    states = [c.get("state") for c in checkpoints]
    if expected_state not in states:
        detail = f"检查点状态: {states}"
        if msg:
            detail = f"{msg}\n{detail}"
        raise AssertionError(f"检查点 {expected_state} 未保存\n{detail}")


def assert_event_published(
    events: list[dict[str, Any]],
    event_type: str,
    msg: str = "",
) -> None:
    """验证指定类型的事件已发布。

    Args:
        events: 事件列表（每个 dict 含 'type' 键）
        event_type: 期望的事件类型
        msg: 额外错误消息
    """
    types = [e.get("type") for e in events]
    if event_type not in types:
        detail = f"已发布事件类型: {types}"
        if msg:
            detail = f"{msg}\n{detail}"
        raise AssertionError(f"事件类型 '{event_type}' 未发布\n{detail}")
