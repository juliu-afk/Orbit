"""网关/熔断专用断言。

验证 LLM 网关的熔断器状态和降级行为。
"""

from __future__ import annotations

from typing import Any


def assert_circuit_state(
    breaker: Any,
    expected_state: str,
    msg: str = "",
) -> None:
    """验证熔断器状态。

    Args:
        breaker: 熔断器实例（含 current_state 属性或 state 属性）
        expected_state: 期望状态（CLOSED/OPEN/HALF_OPEN）
        msg: 额外错误消息
    """
    actual = getattr(breaker, "current_state", None) or getattr(breaker, "state", "UNKNOWN")
    actual = actual.upper() if isinstance(actual, str) else str(actual)

    detail = f"熔断器状态: {actual}"
    if msg:
        detail = f"{msg}\n{detail}"
    assert actual == expected_state.upper(), (
        f"期望熔断器状态 '{expected_state}', 实际 '{actual}'\n{detail}"
    )


def assert_fallback_triggered(
    responses: list[Any],
    from_model: str,
    to_model: str,
    msg: str = "",
) -> None:
    """验证降级触发——from_model 失败后降级到 to_model。

    Args:
        responses: LLMResponse 列表
        from_model: 原始模型
        to_model: 降级目标模型
        msg: 额外错误消息
    """
    # 检查是否有 degraded=True 的响应且 model 变为 to_model
    fallback_found = False
    models_seen = []

    for r in responses:
        model = getattr(r, "model", "")
        degraded = getattr(r, "degraded", False)
        models_seen.append(model)
        if degraded and model == to_model:
            fallback_found = True
            break

    detail = f"模型序列: {models_seen}"
    if msg:
        detail = f"{msg}\n{detail}"
    assert fallback_found, (
        f"未检测到从 {from_model} 到 {to_model} 的降级\n{detail}"
    )
