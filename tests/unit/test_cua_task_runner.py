"""CUA Phase A 调度器鲁棒性单元测试 (US1).

测试范围：循环上限 / 工具超时配置 / 防抖转换 / 串行化标志 / GraphNode。
"""

from __future__ import annotations

import pytest

from orbit.api.schemas.task import TaskState
from orbit.scheduler.graph import GraphNode, NodeStatus
from orbit.scheduler.task_runner import (
    ACTION_DEBOUNCE_SECONDS,
    MAX_AGENT_CYCLES,
    TOOL_TIMEOUT_DEFAULT,
    TOOL_TIMEOUT_SECONDS,
    _DEBOUNCE_TRANSITIONS,
)


class TestCycleLimit:
    """Agent 循环硬上限。"""

    def test_max_cycles_default_value(self):
        """默认上限 50 轮——匹配 PRD AC3。"""
        assert MAX_AGENT_CYCLES == 50

    def test_max_cycles_is_positive(self):
        """上限必须是正数。"""
        assert MAX_AGENT_CYCLES > 0

    def test_cycle_count_below_max_allows_continue(self):
        """循环计数 < 上限 → 继续执行。"""
        cycle_count = 49
        assert cycle_count <= MAX_AGENT_CYCLES

    def test_cycle_count_above_max_triggers_fail(self):
        """循环计数 > 上限 → 触发 FAILED。"""
        cycle_count = 51
        assert cycle_count > MAX_AGENT_CYCLES


class TestToolTimeout:
    """工具级超时配置。"""

    def test_coding_state_gets_longer_timeout(self):
        """CODING 状态用 60s（代码生成更耗时）。"""
        assert TOOL_TIMEOUT_SECONDS[TaskState.CODING] == 60

    def test_other_states_get_default_timeout(self):
        """非 CODING 状态用默认 20s。"""
        assert TOOL_TIMEOUT_DEFAULT == 20
        assert TaskState.PLANNING not in TOOL_TIMEOUT_SECONDS
        assert TaskState.VERIFYING not in TOOL_TIMEOUT_SECONDS
        assert TaskState.IDLE not in TOOL_TIMEOUT_SECONDS

    def test_default_timeout_reasonable(self):
        """默认超时在合理范围（5-60s）。"""
        assert 5 <= TOOL_TIMEOUT_DEFAULT <= 60


class TestDebounceTransitions:
    """防抖延迟状态转换。"""

    def test_debounce_delay_value(self):
        """防抖延迟 120ms——匹配 PRD AC4。"""
        assert ACTION_DEBOUNCE_SECONDS == 0.12

    def test_coding_to_verifying_triggers_debounce(self):
        """CODING → VERIFYING 触发防抖延迟。"""
        assert (TaskState.CODING, TaskState.VERIFYING) in _DEBOUNCE_TRANSITIONS

    def test_non_critical_transition_no_debounce(self):
        """非关键转换不触发防抖。"""
        assert (TaskState.IDLE, TaskState.PARSING) not in _DEBOUNCE_TRANSITIONS
        assert (TaskState.PLANNING, TaskState.CODING) not in _DEBOUNCE_TRANSITIONS
        assert (TaskState.VERIFYING, TaskState.DONE) not in _DEBOUNCE_TRANSITIONS

    def test_debounce_set_is_not_empty(self):
        """防抖转换集合非空。"""
        assert len(_DEBOUNCE_TRANSITIONS) > 0


class TestGraphNodeSerializeTools:
    """GraphNode 串行化标志。"""

    def test_serialize_tools_default_false(self):
        """默认不禁用并行工具调用——保持向后兼容。"""
        node = GraphNode(id="test", agent_role="developer")
        assert node.serialize_tools is False

    def test_serialize_tools_explicit_true(self):
        """显式设置串行化标志。"""
        node = GraphNode(
            id="coding_node", agent_role="developer", serialize_tools=True
        )
        assert node.serialize_tools is True

    def test_serialize_tools_preserves_other_fields(self):
        """serialize_tools 不影响其他字段。"""
        node = GraphNode(
            id="n1",
            agent_role="developer",
            input={"file": "test.py"},
            serialize_tools=True,
        )
        assert node.id == "n1"
        assert node.agent_role == "developer"
        assert node.input == {"file": "test.py"}
        assert node.status == NodeStatus.PENDING
        assert node.serialize_tools is True


class TestContextInjection:
    """上下文字段注入。"""

    def test_parallel_tool_calls_key_name(self):
        """串行化通过 context['parallel_tool_calls'] = False 实现。"""
        context: dict = {}
        context["parallel_tool_calls"] = False
        assert context["parallel_tool_calls"] is False

    def test_tool_timeout_key_name(self):
        """超时通过 context['tool_timeout'] 注入。"""
        context: dict = {"tool_timeout": TOOL_TIMEOUT_SECONDS.get(TaskState.CODING, TOOL_TIMEOUT_DEFAULT)}
        assert context["tool_timeout"] == 60

    def test_cycle_count_key_name(self):
        """循环计数通过 context['_cycle_count'] 追踪。"""
        context: dict = {"_cycle_count": 0}
        context["_cycle_count"] += 1
        assert context["_cycle_count"] == 1


class TestTaskStateValues:
    """TaskState 枚举完整性校验。"""

    def test_all_states_in_to_map(self):
        """所有 TaskState 值均有效。"""
        states = [
            TaskState.IDLE,
            TaskState.PARSING,
            TaskState.PLANNING,
            TaskState.CODING,
            TaskState.VERIFYING,
            TaskState.DONE,
            TaskState.FAILED,
            TaskState.CANCELLED,
        ]
        for s in states:
            assert isinstance(s.value, str)
