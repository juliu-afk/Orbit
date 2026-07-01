"""Orbit 专用断言——会计式精确校验。

纯函数，零依赖——只操作 Python 标准类型和 Orbit Pydantic 模型。
所有断言失败时给出明确的中文错误消息。
"""

from tests.lib.assertions.gateway import assert_circuit_state, assert_fallback_triggered
from tests.lib.assertions.hallucination import assert_layer_blocked, assert_layer_passed
from tests.lib.assertions.sandbox import assert_execution_isolated
from tests.lib.assertions.task import (
    assert_checkpoint_saved,
    assert_event_published,
    assert_state_transition,
)

__all__ = [
    # Task/状态机
    "assert_state_transition",
    "assert_checkpoint_saved",
    "assert_event_published",
    # 防幻觉
    "assert_layer_passed",
    "assert_layer_blocked",
    # 网关/熔断
    "assert_circuit_state",
    "assert_fallback_triggered",
    # 沙箱
    "assert_execution_isolated",
]
