"""防幻觉层专用断言。

验证 L1-L8 防幻觉层的通过/拦截行为。
"""

from __future__ import annotations

from typing import Any

LAYER_NAMES = {
    "L1": "静态图谱校验",
    "L2": "动态追踪校验",
    "L3": "熵监控",
    "L4": "类型校验",
    "L5": "Z3形式化验证",
    "L6": "合约验证",
    "L7": "运行时校验",
    "L8": "配置漂移检测",
}


def assert_layer_passed(
    result: dict[str, Any],
    layer: str,
    msg: str = "",
) -> None:
    """验证防幻觉层通过检测。

    Args:
        result: 防幻觉检测结果 dict（含 "layers" 键，值为 {layer: True/False}）
        layer: 层名称（L1-L8）
        msg: 额外错误消息
    """
    layers = result.get("layers", {})
    passed = layers.get(layer, False)
    layer_name = LAYER_NAMES.get(layer, layer)

    detail = f"防幻觉层检测结果: {layers}"
    if msg:
        detail = f"{msg}\n{detail}"
    assert passed, f"{layer} {layer_name} 未通过\n{detail}"


def assert_layer_blocked(
    result: dict[str, Any],
    layer: str,
    reason_contains: str = "",
    msg: str = "",
) -> None:
    """验证防幻觉层拦截了异常输出。

    Args:
        result: 防幻觉检测结果 dict
        layer: 层名称（L1-L8）
        reason_contains: 拦截原因应包含的子串（空字符串→不检查）
        msg: 额外错误消息
    """
    layers = result.get("layers", {})
    blocked = not layers.get(layer, True)
    reasons = result.get("reasons", {})
    reason = reasons.get(layer, "")
    layer_name = LAYER_NAMES.get(layer, layer)

    detail = f"防幻觉层检测: layers={layers}, reasons={reasons}"
    if msg:
        detail = f"{msg}\n{detail}"

    assert blocked, f"{layer} {layer_name} 应拦截但通过了\n{detail}"

    if reason_contains:
        assert reason_contains in reason, (
            f"{layer} {layer_name} 拦截原因不匹配: 期望包含 '{reason_contains}', 实际 '{reason}'"
        )
