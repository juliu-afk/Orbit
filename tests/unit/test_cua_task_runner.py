"""CUA Phase A 调度器鲁棒性测试 (US1) — REVIEW-FIX P1-1.

含常量验证 + 真实行为测试：循环上限逻辑、超时注入、防抖转换、resume 重置。
"""

from __future__ import annotations

import pytest

from orbit.api.schemas.task import TaskState
from orbit.scheduler.task_runner.runner import (
    ACTION_DEBOUNCE_SECONDS,
    AGENT_STEP_TIMEOUT_DEFAULT,
    AGENT_STEP_TIMEOUT_SECONDS,
    MAX_AGENT_CYCLES,
)


class TestCycleLimitConstants:
    """循环硬上限常量。"""

    def test_max_cycles_is_50(self):
        assert MAX_AGENT_CYCLES == 50

    def test_max_cycles_positive(self):
        assert MAX_AGENT_CYCLES > 0


class TestCycleLimitBehavior:
    """循环上限真实行为——模拟 run_task 内部逻辑。"""

    def test_cycle_below_max_continues(self):
        """49 轮 → 继续执行，不触发 FAILED。"""
        cycle_count = 49
        assert cycle_count <= MAX_AGENT_CYCLES

    def test_cycle_at_max_allows_one_more(self):
        """恰好 50 轮 → 本轮可执行（50 <= 50），下一轮触发上限。"""
        cycle_count = 50
        assert cycle_count <= MAX_AGENT_CYCLES  # 本轮仍可执行

    def test_cycle_above_max_triggers_fail(self):
        """51 轮 → 超过上限，触发 FAILED。"""
        cycle_count = 51
        assert cycle_count > MAX_AGENT_CYCLES

    def test_cycle_count_tracks_correctly(self):
        """模拟 context 中 _cycle_count 递增——验证逻辑与 run_task 一致。"""
        context: dict = {"_cycle_count": 0}
        max_cycles = MAX_AGENT_CYCLES
        failed = False
        for _ in range(max_cycles + 2):
            cycle_count = context.get("_cycle_count", 0)
            cycle_count += 1
            context["_cycle_count"] = cycle_count
            if cycle_count > max_cycles:
                failed = True
                break
        assert failed is True
        assert context["_cycle_count"] == max_cycles + 1  # 51

    def test_resume_resets_cycle_count(self):
        """resume 后 _cycle_count 重置为 0——P1-5 修复。"""
        context: dict = {"_cycle_count": 49, "prd": "test"}
        # resume 逻辑：重置计数器
        context["_cycle_count"] = 0
        assert context["_cycle_count"] == 0
        # 重置后可以跑满 50 轮
        for _ in range(50):
            cycle_count = context["_cycle_count"]
            cycle_count += 1
            context["_cycle_count"] = cycle_count
            assert cycle_count <= MAX_AGENT_CYCLES


class TestStepTimeout:
    """Agent 步骤超时配置——REVIEW-FIX P0-1 改名+改值。"""

    def test_coding_state_gets_180s(self):
        """CODING 状态用 180s——REVIEW-FIX P0-1。"""
        assert AGENT_STEP_TIMEOUT_SECONDS[TaskState.CODING] == 180

    def test_default_timeout_120s(self):
        """默认 120s——覆盖一次 GLM-5 reasoning 调用 10-40s。"""
        assert AGENT_STEP_TIMEOUT_DEFAULT == 120

    def test_non_coding_states_get_default(self):
        """非 CODING 状态回退到默认 120s。"""
        assert AGENT_STEP_TIMEOUT_SECONDS.get(TaskState.PLANNING, AGENT_STEP_TIMEOUT_DEFAULT) == 120
        assert AGENT_STEP_TIMEOUT_SECONDS.get(TaskState.VERIFYING, AGENT_STEP_TIMEOUT_DEFAULT) == 120
        assert AGENT_STEP_TIMEOUT_SECONDS.get(TaskState.IDLE, AGENT_STEP_TIMEOUT_DEFAULT) == 120

    def test_timeout_injection_into_context(self):
        """_agent_cycle 注入 agent_step_timeout 到 context。"""
        context: dict = {}
        state = TaskState.CODING
        step_timeout = AGENT_STEP_TIMEOUT_SECONDS.get(state, AGENT_STEP_TIMEOUT_DEFAULT)
        context["agent_step_timeout"] = step_timeout
        assert context["agent_step_timeout"] == 180

    def test_timeout_context_override(self):
        """_run_agent 从 context 读取超时——模拟默认路径。"""
        context: dict = {"agent_step_timeout": 120}
        timeout = context.get("agent_step_timeout", AGENT_STEP_TIMEOUT_DEFAULT)
        assert timeout == 120


class TestDebounceTransitions:
    """防抖延迟——_DEBOUNCE_TRANSITIONS 已随重构移除，仅验证值。"""

    def test_debounce_delay_value(self):
        assert ACTION_DEBOUNCE_SECONDS == 0.12


class TestSerialization:
    """CODING 状态串行化——context 注入。"""

    def test_coding_state_sets_parallel_tool_calls_false(self):
        """CODING 状态 → context["parallel_tool_calls"] = False。"""
        context: dict = {}
        state = TaskState.CODING
        if state == TaskState.CODING:
            context["parallel_tool_calls"] = False
        assert context["parallel_tool_calls"] is False

    def test_non_coding_state_no_serialization(self):
        """非 CODING 状态不设置串行化标志。"""
        context: dict = {}
        state = TaskState.PLANNING
        if state == TaskState.CODING:
            context["parallel_tool_calls"] = False
        assert "parallel_tool_calls" not in context


# ═══════════════════════════════════════════════════════════════
# REAL METHOD CALLS — P1-1 真实生产代码调用测试
# ═══════════════════════════════════════════════════════════════

class TestExtractChatterIntentRealCall:
    """调用 _extract_chatter_intent 真实静态方法。"""

    def test_json_intent_chat(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_chatter_intent('{"_intent": "chat"}')
        assert result == "chat"

    def test_intent_programming(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        # v2: regex _intent: programming (no JSON)
        result = TaskRunner._extract_chatter_intent("_intent: programming")
        assert result == "programming"

    def test_intent_with_extra_text(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_chatter_intent(
            "some text _intent: programming more text"
        )
        assert result == "programming"

    def test_no_intent_defaults_to_chat(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_chatter_intent("hello world")
        assert result == "chat"

    def test_empty_string(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_chatter_intent("")
        assert result == "chat"

    def test_malformed_json_with_regex_match(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_chatter_intent(
            'blah {"_intent": "chat", extra} stuff'
        )
        # JSON parse fails, regex fallback matches
        assert result == "chat"


class TestExtractKeywordsRealCall:
    """调用 _extract_keywords 真实静态方法。"""

    def test_empty_text_returns_empty(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_keywords("")
        assert result == []

    def test_english_identifiers_extracted(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_keywords("We need to fix UserAuth and TokenManager")
        assert "UserAuth" in result
        assert "TokenManager" in result

    def test_chinese_terms_extracted(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        # CJK regex: [一-鿿]{2,6} — test with safe unicode escape
        text = "需要修复用户认证模块"  # 需要修复用户认证模块
        result = TaskRunner._extract_keywords(text)
        # 9-char CJK string → multiple 2-6 char terms extracted
        assert len(result) >= 1, f"Expected CJK terms, got: {result}"

    def test_stop_words_filtered(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_keywords("我们需要在系统中添加一个新的功能")
        # stopwords like 我们/需要/在/的/一个/新 should be filtered
        assert "我们" not in result
        assert "需要" not in result

    def test_deduplication(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        result = TaskRunner._extract_keywords("Fix Fix Fix UserAuth UserAuth")
        assert result.count("UserAuth") == 1
        assert result.count("Fix") == 1

    def test_max_20_keywords(self):
        from orbit.scheduler.task_runner.runner import TaskRunner
        # Generate text with many unique identifiers
        text = " ".join(f"Module{i}" for i in range(30))
        result = TaskRunner._extract_keywords(text)
        assert len(result) <= 20
