"""覆盖率补测——goal/dependency_analyzer、compression/cascade、compression/budget、goal/models。

目标文件及原覆盖率:
- compression/cascade.py ~11%: CascadePruner 级联裁剪
- compression/budget.py ~0%: TokenBudgetTracker 预算跟踪
- goal/dependency_analyzer.py ~8%: DependencyAnalyzer 依赖分析
- goal/models.py ~0%: GoalSession/GoalResult/SubTaskResult 等数据模型
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.compression.budget import TokenBudgetTracker
from orbit.compression.cascade import CascadePruner
from orbit.compression.models import CompressionAction, CompressionThreshold
from orbit.goal.dependency_analyzer import DependencyAnalyzer
from orbit.goal.models import (
    DepEdge,
    DependencyConflict,
    GoalBatchReport,
    GoalResult,
    GoalSession,
    IntakeDecision,
    SubTaskResult,
)


# =============================================================================
# CascadePruner —— 级联上下文裁剪器
# =============================================================================


class TestCascadePrunerPure:
    """CascadePruner 纯函数 + 简单场景。"""

    def test_is_error_output_detects_traceback(self) -> None:
        """错误标记 Traceback → 识别为错误输出。"""
        assert CascadePruner._is_error_output("Traceback (most recent call last):\n  File ...")

    def test_is_error_output_detects_failed(self) -> None:
        """FAILED → 识别为错误输出。"""
        assert CascadePruner._is_error_output("FAILED tests/test_x.py::test_y")

    def test_is_error_output_detects_chinese_error(self) -> None:
        """中文"错误" → 识别为错误输出。"""
        assert CascadePruner._is_error_output("发生错误：连接超时")

    def test_is_error_output_normal_text(self) -> None:
        """普通文本 → 不是错误输出。"""
        assert not CascadePruner._is_error_output("All tests passed successfully.")

    def test_is_error_output_empty_string(self) -> None:
        """空字符串 → 不是错误输出。"""
        assert not CascadePruner._is_error_output("")

    def test_prune_if_needed_budget_none(self) -> None:
        """budget=None → 立即返回，无操作。"""
        pruner = CascadePruner()
        messages = [{"role": "user", "content": "hello"}]

        result = asyncio_run(pruner.prune_if_needed(messages, budget=None))

        assert result[0] == messages  # 原列表不变
        assert result[1] == []  # 无 stage 应用
        assert result[2] == 0  # 0 bytes 移除

    def test_prune_if_needed_budget_skip(self) -> None:
        """budget.check_threshold()=SKIP → no-op。"""
        pruner = CascadePruner()
        budget = MagicMock()
        budget.check_threshold.return_value = CompressionAction.SKIP
        messages = [{"role": "user", "content": "hello"}]

        result = asyncio_run(pruner.prune_if_needed(messages, budget=budget))

        assert result[0] == messages
        assert result[1] == []

    def test_prune_if_needed_empty_messages(self) -> None:
        """空消息列表 → 正常返回空。"""
        pruner = CascadePruner()
        budget = MagicMock()
        budget.check_threshold.return_value = CompressionAction.FORCE
        # 空列表，Stage 1 无任何匹配 → 返回空
        result = asyncio_run(pruner.prune_if_needed([], budget=budget))

        assert result[0] == []
        assert "strip_consumed" in result[1]

    def test_finish_metrics_calculation(self) -> None:
        """_finish 正确计算压缩指标。"""
        pruner = CascadePruner()
        original = [{"role": "user", "content": "hello world this is a test message"}]
        compressed = [{"role": "user", "content": "hello"}]
        # _stages_applied 由 prune_if_needed 填充，这里手动设置以测试 _finish
        pruner._stages_applied = ["strip_consumed"]

        messages, stages, removed = pruner._finish(compressed, original_size=sum(len(str(m)) for m in original))

        assert messages == compressed
        assert stages == ["strip_consumed"]
        assert removed > 0

    def test_stage1_strip_consumed_large_consumed_output(self) -> None:
        """Stage 1: 大输出且已被消费 → 替换为摘要占位。"""
        pruner = CascadePruner(large_output_threshold=10)
        messages = [
            {"role": "user", "content": "do something"},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "x" * 100,  # 超阈值
            },
            # assistant 有实质性内容 → 标记 tool 输出"已消费"
            {"role": "assistant", "content": "Based on the file content, I will make changes."},
        ]

        result = pruner._stage1_strip_consumed(messages, memory=None)

        # tool 消息被替换为摘要占位
        assert len(result) == 3
        tool_msg = result[1]
        assert "[上下文裁剪]" in tool_msg["content"]
        assert "100 字符" in tool_msg["content"]

    def test_stage1_preserves_error_output(self) -> None:
        """Stage 1: 错误输出即使很大也被保留。"""
        pruner = CascadePruner(large_output_threshold=10)
        messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "Traceback: " + "x" * 200},
            {"role": "assistant", "content": "Found an error, fixing it."},
        ]

        result = pruner._stage1_strip_consumed(messages, memory=None)

        # 错误输出保留原始内容
        assert len(result) == 2
        assert result[0]["content"].startswith("Traceback:")

    def test_stage1_skips_small_output(self) -> None:
        """Stage 1: 小于阈值的输出不被处理。"""
        pruner = CascadePruner(large_output_threshold=5000)
        messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "small output"},
            {"role": "assistant", "content": "OK"},
        ]

        result = pruner._stage1_strip_consumed(messages, memory=None)

        assert len(result) == 2
        assert result[0]["content"] == "small output"

    def test_stage2_removes_ineffectual_reasoning(self) -> None:
        """Stage 2: 连续无效果推理被移除（超过 max_ineffectual 的 assistant 被跳过）。"""
        pruner = CascadePruner(ineffectual_min_chars=50)
        messages = [
            {"role": "assistant", "content": "short"},  # 短内容 + 无 tool_calls → 无效果
            {"role": "assistant", "content": "nah"},  # 连续第2个
            {"role": "assistant", "content": "no"},  # 连续第3个
            {"role": "assistant", "content": "ok"},  # 连续第4个 > max_ineffectual(3) → 移除
            {"role": "tool", "content": "result"},  # 对应的 tool 消息（由于 consecutive > max+1=4 为否 → 保留）
        ]

        result = pruner._stage2_remove_effectless(messages, memory=None)

        # 第4个 assistant ("ok") 被移除，其余保留
        assert len(result) == 4
        contents = [m["content"] for m in result]
        assert "ok" not in contents  # 第4个被移除

    def test_stage2_preserves_tool_call_assistant(self) -> None:
        """Stage 2: 有 tool_calls 的 assistant 不被视为无效果。"""
        pruner = CascadePruner()
        messages = [
            {"role": "assistant", "content": "short", "tool_calls": [{"id": "call_1"}]},
        ]

        result = pruner._stage2_remove_effectless(messages, memory=None)

        assert len(result) == 1

    def test_stage2_records_failure_to_memory(self) -> None:
        """Stage 2: 移除无效果推理时记录到 memory.failed_approaches。"""
        pruner = CascadePruner(ineffectual_min_chars=10)
        memory = MagicMock()
        messages = [
            {"role": "assistant", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "assistant", "content": "c"},
            {"role": "assistant", "content": "d"},  # 第4个 → 移除 + record_failure
        ]

        pruner._stage2_remove_effectless(messages, memory=memory)

        memory.record_failure.assert_called_once()

    def test_stage3_structured_summary_no_memory(self) -> None:
        """Stage 3: memory 不支持 to_progress_injection → 原样返回。"""
        pruner = CascadePruner()
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]

        # memory 没有 to_progress_injection 方法 → 跳过
        result = pruner._stage3_structured_summary(messages, memory=object())

        assert result == messages

    def test_stage3_structured_summary_few_messages(self) -> None:
        """Stage 3: 消息太少（≤2 条非尾部）→ 不值得压缩。"""
        pruner = CascadePruner()
        memory = MagicMock()
        memory.to_progress_injection.return_value = "progress text"
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "hi"},
        ]

        result = pruner._stage3_structured_summary(messages, memory=memory)

        # head_messages ≤2 → 直接返回原列表
        assert result == messages

    def test_stage3_with_memory_compresses_old_turns(self) -> None:
        """Stage 3: 有 memory → 旧轮次被进度摘要替代。

        布局: system + 6 轮 user/assistant → 保留尾部 5 个 assistant + 压缩头部。
        head_messages 需 >2 条才触发压缩，因此准备 3 轮旧消息在前。
        """
        pruner = CascadePruner()
        memory = MagicMock()
        memory.to_progress_injection.return_value = "已完成 A，进行中 B"
        messages = [
            {"role": "system", "content": "system prompt"},
            # 前 3 轮（6 条消息）→ head，会被压缩
            {"role": "user", "content": "old 1 user"},
            {"role": "assistant", "content": "old 1 asst"},
            {"role": "user", "content": "old 2 user"},
            {"role": "assistant", "content": "old 2 asst"},
            {"role": "user", "content": "old 3 user"},
            {"role": "assistant", "content": "old 3 asst"},
            # 后 3 轮（6 条消息）→ tail，被保留
            {"role": "user", "content": "mid user"},
            {"role": "assistant", "content": "mid asst"},
            {"role": "user", "content": "recent user"},
            {"role": "assistant", "content": "recent asst"},
            {"role": "user", "content": "latest user"},
            {"role": "assistant", "content": "latest asst"},
        ]

        result = pruner._stage3_structured_summary(messages, memory=memory)

        # system 被保留，旧消息被压缩为进度摘要，尾部最近消息保留
        assert result[0]["role"] == "system"
        # 第2条是一个 system 占位（结构化进度恢复）
        assert result[1]["role"] == "system"
        assert "结构化进度恢复" in result[1]["content"]
        assert "3 条早期消息" in result[1]["content"]
        # 尾部消息保留——压缩后总条数应小于原始
        assert result[-1]["content"] == "latest asst"
        assert len(result) < len(messages)  # 确实被压缩

    def test_is_consumed_returns_true_without_followup(self) -> None:
        """_is_consumed: 后续无 assistant 消息 → 已消费。"""
        pruner = CascadePruner(consumed_output_max_turns=3)
        tool_msg = {"role": "tool", "content": "large output here"}
        messages = [tool_msg, {"role": "user", "content": "continue"}]

        # user 消息不是 assistant → 认为已消费
        assert pruner._is_consumed(tool_msg, messages, 0)

    def test_is_consumed_returns_false_with_recent_tool_calls(self) -> None:
        """_is_consumed: 后续有 tool_calls → 处理中，未消费。"""
        pruner = CascadePruner(consumed_output_max_turns=3)
        tool_msg = {"role": "tool", "content": "large output"}
        messages = [
            tool_msg,
            {"role": "assistant", "content": "", "tool_calls": [{"id": "call_2"}]},
        ]

        assert not pruner._is_consumed(tool_msg, messages, 0)

    def test_is_consumed_empty_content(self) -> None:
        """_is_consumed: 空 content → 未消费（不处理）。"""
        pruner = CascadePruner()
        tool_msg = {"role": "tool", "content": ""}

        assert not pruner._is_consumed(tool_msg, [tool_msg], 0)

    def test_properties_stages_and_bytes(self) -> None:
        """属性 stages_applied / bytes_removed 正确反映内部状态。"""
        pruner = CascadePruner()
        pruner._stages_applied = ["strip_consumed", "remove_ineffectual"]
        pruner._bytes_removed_total = 5000

        assert pruner.stages_applied == ["strip_consumed", "remove_ineffectual"]
        assert pruner.bytes_removed == 5000


# =============================================================================
# TokenBudgetTracker —— Token 预算跟踪器
# =============================================================================


class TestTokenBudgetTracker:
    """TokenBudgetTracker 纯函数测试（mock count_tokens 避免依赖 tiktoken）。"""

    def test_check_threshold_skip_when_under_soft(self) -> None:
        """使用率低于 soft_warning (50%) → SKIP。"""
        tracker = TokenBudgetTracker(max_context_window=100_000, reserved_output=0)
        tracker.record_usage(10_000)  # 10%
        assert tracker.check_threshold() == CompressionAction.SKIP

    def test_check_threshold_warn_when_between_thresholds(self) -> None:
        """使用率在 soft_warning~hard_limit (50-85%) → WARN。"""
        tracker = TokenBudgetTracker(max_context_window=100_000, reserved_output=0)
        tracker.record_usage(60_000)  # 60%
        assert tracker.check_threshold() == CompressionAction.WARN

    def test_check_threshold_force_when_over_hard(self) -> None:
        """使用率超过 hard_limit (85%) → FORCE。"""
        tracker = TokenBudgetTracker(max_context_window=100_000, reserved_output=0)
        tracker.record_usage(90_000)  # 90%
        assert tracker.check_threshold() == CompressionAction.FORCE

    def test_check_threshold_custom_threshold(self) -> None:
        """自定义阈值生效。"""
        threshold = CompressionThreshold(soft_warning=0.3, hard_limit=0.6)
        tracker = TokenBudgetTracker(max_context_window=100_000, reserved_output=0, threshold=threshold)
        tracker.record_usage(50_000)  # 50% → 在 30-60% 之间 → WARN
        assert tracker.check_threshold() == CompressionAction.WARN

    def test_would_exceed_returns_true(self) -> None:
        """would_exceed: 添加后超限 → True。"""
        tracker = TokenBudgetTracker(max_context_window=100_000, reserved_output=0)
        tracker.record_usage(80_000)
        assert tracker.would_exceed(10_000)  # 90k/100k = 90% > 85%

    def test_would_exceed_returns_false(self) -> None:
        """would_exceed: 添加后仍在限内 → False。"""
        tracker = TokenBudgetTracker(max_context_window=100_000, reserved_output=0)
        tracker.record_usage(50_000)
        assert not tracker.would_exceed(10_000)  # 60k/100k = 60% < 85%

    def test_would_exceed_zero_denom(self) -> None:
        """reserved_output 等于 max_context → 分母为 0 → 返回 True。"""
        tracker = TokenBudgetTracker(max_context_window=100, reserved_output=100)
        assert tracker.would_exceed(1)

    @patch("orbit.compression.budget.count_tokens", return_value=10)
    def test_estimate_tokens_simple(self, mock_count) -> None:
        """estimate_tokens: 简单消息列表。"""
        tracker = TokenBudgetTracker()
        messages = [{"role": "user", "content": "hello world"}, {"role": "assistant", "content": "hi"}]
        total = tracker.estimate_tokens(messages)
        # 每条 content=10tokens + 20 overhead = 30, 两条 = 60
        assert total == 60

    @patch("orbit.compression.budget.count_tokens", return_value=5)
    def test_estimate_tokens_with_tool_calls(self, mock_count) -> None:
        """estimate_tokens: 含 tool_calls 的消息被计入。"""
        tracker = TokenBudgetTracker()
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file"}}]},
        ]
        total = tracker.estimate_tokens(messages)
        # content="" → count_tokens 不调用，但 20 overhead 计入; tool_calls str → count_tokens 调用
        assert total > 0

    def test_estimate_tokens_empty_messages(self) -> None:
        """estimate_tokens: 空列表 → 1。"""
        tracker = TokenBudgetTracker()
        assert tracker.estimate_tokens([]) == 1

    def test_available_and_usage_ratio(self) -> None:
        """available 和 usage_ratio 属性正确。"""
        tracker = TokenBudgetTracker(max_context_window=128_000, reserved_output=4_000)
        tracker.record_usage(50_000)
        # available = 128000 - 4000 - 50000 = 74000
        assert tracker.available == 74_000
        # usage_ratio = 50000 / (128000 - 4000) ≈ 0.403
        assert tracker.usage_ratio == pytest.approx(50000 / 124000)

    @patch("orbit.compression.budget.count_tokens")
    def test_estimate_tokens_only_str_content(self, mock_count) -> None:
        """estimate_tokens: 非字符串 content 被安全跳过。"""
        mock_count.return_value = 10
        tracker = TokenBudgetTracker()
        messages = [{"role": "tool", "content": {"file": "data"}}]
        total = tracker.estimate_tokens(messages)
        # dict content → `if isinstance(content, str) and content` 为 False → 仅 20 overhead
        assert total > 0  # 有基础开销


# =============================================================================
# DependencyAnalyzer —— 依赖分析
# =============================================================================


class TestDependencyAnalyzerBasic:
    """DependencyAnalyzer 基础功能——纯函数 / 少量 mocking。"""

    def test_analyze_empty_goals(self) -> None:
        """空 Goal 列表。"""
        analyzer = DependencyAnalyzer()
        result = asyncio_run(analyzer.analyze([]))
        assert result["layers"] == [[]]
        assert result["edges"] == []
        assert result["conflicts"] == []

    def test_analyze_single_goal(self) -> None:
        """单个 Goal → 单层。"""
        goal = GoalSession(description="单任务")
        analyzer = DependencyAnalyzer()
        result = asyncio_run(analyzer.analyze([goal]))
        assert len(result["layers"]) == 1
        assert result["layers"][0] == [goal]
        assert result["edges"] == []

    def test_analyze_no_deps(self) -> None:
        """多个 Goal 但无依赖 → 单层。"""
        g1 = GoalSession(id="g1", description="任务A")
        g2 = GoalSession(id="g2", description="任务B")
        analyzer = DependencyAnalyzer()
        result = asyncio_run(analyzer.analyze([g1, g2]))
        assert len(result["layers"]) == 1

    def test_extract_explicit_depends_on_frontmatter(self) -> None:
        """提取显式依赖: frontmatter depends_on。"""
        g1 = GoalSession(id="g1", description="基础模块")
        g2 = GoalSession(id="g2", description="depends_on: [\"基础模块\"]")
        analyzer = DependencyAnalyzer()
        edges = analyzer._extract_explicit_deps([g1, g2])
        # g1 → g2
        assert len(edges) == 1
        assert edges[0].from_id == "g1"
        assert edges[0].to_id == "g2"
        assert edges[0].type == "explicit"

    def test_extract_explicit_depends_on_tag(self) -> None:
        """提取显式依赖: @depends-on 标签。"""
        g1 = GoalSession(id="g1", description="认证模块")
        g2 = GoalSession(id="g2", description="登录页面 @depends-on 认证模块")
        analyzer = DependencyAnalyzer()
        edges = analyzer._extract_explicit_deps([g1, g2])
        assert len(edges) == 1
        assert edges[0].from_id == "g1"
        assert edges[0].to_id == "g2"

    def test_extract_explicit_self_ref_skipped(self) -> None:
        """依赖自身 → 不生成边（后续会作为冲突检测）。"""
        g1 = GoalSession(id="g1", description="depends_on: [\"自身模块\"]")
        # 找不到此名称，无匹配边
        analyzer = DependencyAnalyzer()
        edges = analyzer._extract_explicit_deps([g1])
        assert len(edges) == 0

    def test_detect_file_conflicts_with_mock(self) -> None:
        """文件冲突检测: 模拟 CodeGraph 返回重叠文件。"""
        codegraph = MagicMock()
        codegraph.search_files = AsyncMock(return_value=["src/a.py", "src/b.py"])
        analyzer = DependencyAnalyzer(codegraph=codegraph)
        g1 = GoalSession(id="g1", description="修改模块A")
        g2 = GoalSession(id="g2", description="修改模块A的测试")

        edges = asyncio_run(analyzer._detect_file_conflicts([g1, g2], codebase_root="."))
        assert len(edges) >= 1
        assert edges[0].type == "file_conflict"
        assert "共享文件" in edges[0].source

    def test_detect_file_conflicts_no_codegraph(self) -> None:
        """无 CodeGraph → 文件冲突检测返回空。"""
        analyzer = DependencyAnalyzer(codegraph=None)
        g1 = GoalSession(id="g1", description="任务")
        g2 = GoalSession(id="g2", description="任务")
        edges = asyncio_run(analyzer._detect_file_conflicts([g1, g2], codebase_root="."))
        assert edges == []

    def test_infer_implicit_deps_no_cheap_llm(self) -> None:
        """无 cheap_llm → 隐式推断返回空。"""
        analyzer = DependencyAnalyzer()
        g1 = GoalSession(id="g1", description="任务A")
        g2 = GoalSession(id="g2", description="任务B")
        edges = asyncio_run(analyzer._infer_implicit_deps([g1, g2]))
        assert edges == []

    def test_infer_implicit_deps_single_goal(self) -> None:
        """单个 Goal → 隐式推断返回空。"""
        analyzer = DependencyAnalyzer(cheap_llm=MagicMock())
        g1 = GoalSession(id="g1", description="任务A")
        edges = asyncio_run(analyzer._infer_implicit_deps([g1]))
        assert edges == []

    def test_infer_implicit_deps_with_mock_llm(self) -> None:
        """模拟 LLM 返回隐式依赖。"""
        cheap_llm = MagicMock()
        resp = MagicMock()
        resp.content = '[{"from": 1, "to": 2, "reason": "任务B依赖任务A的API"}]'
        cheap_llm.generate = AsyncMock(return_value=resp)
        analyzer = DependencyAnalyzer(cheap_llm=cheap_llm)
        g1 = GoalSession(id="g1", description="实现API")
        g2 = GoalSession(id="g2", description="前端对接")

        edges = asyncio_run(analyzer._infer_implicit_deps([g1, g2]))
        assert len(edges) == 1
        assert edges[0].type == "implicit"
        assert edges[0].from_id == "g1"
        assert edges[0].to_id == "g2"
        assert edges[0].confidence == 0.6

    def test_infer_implicit_deps_llm_returns_empty(self) -> None:
        """LLM 返回空数组 → 无边。"""
        cheap_llm = MagicMock()
        resp = MagicMock()
        resp.content = "[]"
        cheap_llm.generate = AsyncMock(return_value=resp)
        analyzer = DependencyAnalyzer(cheap_llm=cheap_llm)
        g1 = GoalSession(id="g1", description="A")
        g2 = GoalSession(id="g2", description="B")

        edges = asyncio_run(analyzer._infer_implicit_deps([g1, g2]))
        assert edges == []

    def test_parse_implicit_response_with_code_block(self) -> None:
        """解析 LLM 响应: markdown 代码块包裹的 JSON。"""
        content = "```json\n[{\"from\": 1, \"to\": 2, \"reason\": \"test\"}]\n```"
        g1 = GoalSession(id="g1", description="A")
        g2 = GoalSession(id="g2", description="B")
        analyzer = DependencyAnalyzer()
        edges = analyzer._parse_implicit_response(content, [g1, g2])
        assert len(edges) == 1

    def test_parse_implicit_response_invalid_json(self) -> None:
        """非法 JSON → 返回空。"""
        analyzer = DependencyAnalyzer()
        edges = analyzer._parse_implicit_response("{invalid", [GoalSession(description="x")])
        assert edges == []

    def test_topological_layers(self) -> None:
        """Kahn 算法: 三层 DAG。"""
        g1 = GoalSession(id="g1", description="底层")
        g2 = GoalSession(id="g2", description="中层")
        g3 = GoalSession(id="g3", description="上层")
        edges = [
            DepEdge(from_id="g1", to_id="g2", type="explicit"),
            DepEdge(from_id="g2", to_id="g3", type="explicit"),
        ]
        analyzer = DependencyAnalyzer()
        layers = analyzer._topological_layers([g1, g2, g3], edges)
        assert len(layers) == 3
        assert layers[0][0].id == "g1"
        assert layers[1][0].id == "g2"
        assert layers[2][0].id == "g3"

    def test_topological_layers_diamond(self) -> None:
        """Kahn 算法: 菱形依赖（两个中层可并行）。"""
        g1 = GoalSession(id="g1", description="根")
        g2 = GoalSession(id="g2", description="左")
        g3 = GoalSession(id="g3", description="右")
        g4 = GoalSession(id="g4", description="汇")
        edges = [
            DepEdge(from_id="g1", to_id="g2", type="explicit"),
            DepEdge(from_id="g1", to_id="g3", type="explicit"),
            DepEdge(from_id="g2", to_id="g4", type="explicit"),
            DepEdge(from_id="g3", to_id="g4", type="explicit"),
        ]
        analyzer = DependencyAnalyzer()
        layers = analyzer._topological_layers([g1, g2, g3, g4], edges)
        assert len(layers) == 3
        assert layers[0][0].id == "g1"
        assert {g.id for g in layers[1]} == {"g2", "g3"}
        assert layers[2][0].id == "g4"

    def test_detect_self_ref_conflict(self) -> None:
        """自依赖检测。"""
        edges = [DepEdge(from_id="g1", to_id="g1", type="explicit")]
        analyzer = DependencyAnalyzer()
        conflicts = analyzer._detect_conflicts([], edges)
        assert any(c.type == "self_ref" for c in conflicts)

    def test_find_cycles_detects_cycle(self) -> None:
        """环形依赖检测: g1→g2→g1。"""
        edges = [
            DepEdge(from_id="g1", to_id="g2", type="explicit"),
            DepEdge(from_id="g2", to_id="g1", type="explicit"),
        ]
        cycles = DependencyAnalyzer._find_cycles(edges)
        assert len(cycles) >= 1
        # 环中包含 g1 和 g2
        all_nodes_in_cycles = set(n for c in cycles for n in c)
        assert "g1" in all_nodes_in_cycles
        assert "g2" in all_nodes_in_cycles

    def test_find_cycles_no_cycle(self) -> None:
        """无环 DAG。"""
        edges = [
            DepEdge(from_id="g1", to_id="g2", type="explicit"),
            DepEdge(from_id="g2", to_id="g3", type="explicit"),
        ]
        cycles = DependencyAnalyzer._find_cycles(edges)
        assert cycles == []

    def test_extract_keywords_english_and_chinese(self) -> None:
        """关键词提取: 英文 + 中文。"""
        desc = "实现用户认证模块 支持 OAuth2 登录"
        keywords = DependencyAnalyzer._extract_keywords(desc)
        assert len(keywords) <= 8
        # 应该包含英文词
        assert any("OAuth2" in k for k in keywords)

    def test_extract_keywords_empty(self) -> None:
        """空描述 → 空列表。"""
        keywords = DependencyAnalyzer._extract_keywords("")
        assert keywords == []

    def test_find_goal_by_exact_id(self) -> None:
        """按 ID 精确匹配。"""
        g1 = GoalSession(id="abc123", description="任务A")
        g2 = GoalSession(id="xyz789", description="任务B")
        result = DependencyAnalyzer._find_goal_by_name([g1, g2], "abc123")
        assert result is not None
        assert result.id == "abc123"

    def test_find_goal_by_description_exact(self) -> None:
        """按描述精确匹配。"""
        g1 = GoalSession(id="g1", description="实现用户认证")
        result = DependencyAnalyzer._find_goal_by_name([g1], "实现用户认证")
        assert result is not None
        assert result.id == "g1"

    def test_find_goal_by_pattern_match(self) -> None:
        """按 word-boundary 正则匹配（g2 中 core-模块在末尾，\b 匹配结尾）。"""
        g1 = GoalSession(id="g1", description="用户-core-模块实现")  # 块后接 \w → 末尾 \b 不匹配
        g2 = GoalSession(id="g2", description="编写 core-模块")     # 块在末尾 → \b 匹配
        result = DependencyAnalyzer._find_goal_by_name([g1, g2], "core-模块")
        assert result is not None
        assert result.id == "g2"


# =============================================================================
# Goal models —— 数据模型
# =============================================================================


class TestGoalModels:
    """GoalSession / GoalResult / SubTaskResult / DepEdge / IntakeDecision。"""

    def test_goal_session_defaults(self) -> None:
        """GoalSession 默认值。"""
        gs = GoalSession(description="测试目标")
        assert gs.id is not None  # uuid 自动生成
        assert gs.description == "测试目标"
        assert gs.constraints == []
        assert gs.verification_commands == []
        assert gs.sub_tasks == {}
        assert gs.spec is None
        assert gs.status == "active"
        assert gs.total_token_budget == 0
        assert gs.max_react == 12
        assert gs.max_parallel_tasks == 5

    def test_goal_session_custom_values(self) -> None:
        """GoalSession 自定义值。"""
        gs = GoalSession(
            id="custom-id",
            description="复杂目标",
            constraints=["内存<1GB"],
            verification_commands=["pytest tests/"],
            sub_tasks={"t1": "running"},
            spec={"steps": []},
            status="done",
            total_token_budget=100_000,
            max_react=5,
            max_parallel_tasks=3,
        )
        assert gs.id == "custom-id"
        assert gs.constraints == ["内存<1GB"]
        assert gs.spec == {"steps": []}
        assert gs.total_token_budget == 100_000

    def test_goal_session_serialization(self) -> None:
        """GoalSession 可序列化为 dict/JSON。"""
        gs = GoalSession(description="可序列化测试")
        d = gs.model_dump()
        assert d["description"] == "可序列化测试"
        assert "id" in d
        assert "created_at" in d

    def test_goal_result_defaults(self) -> None:
        """GoalResult 默认值。"""
        gr = GoalResult()
        assert gr.status == "pending"
        assert gr.reason == ""
        assert gr.tasks_completed == 0
        assert gr.tasks_failed == 0
        assert gr.total_tokens == 0
        assert gr.total_time_seconds == 0.0
        assert gr.report_path == ""

    def test_goal_result_custom(self) -> None:
        """GoalResult 自定义值。"""
        gr = GoalResult(
            status="done",
            reason="全部通过",
            tasks_completed=5,
            tasks_failed=1,
            total_tokens=50_000,
            total_time_seconds=120.5,
            report_path="/tmp/report.md",
        )
        assert gr.status == "done"
        assert gr.reason == "全部通过"
        assert gr.tasks_completed == 5

    def test_sub_task_result_defaults(self) -> None:
        """SubTaskResult 默认值。"""
        sr = SubTaskResult()
        assert sr.task_id == ""
        assert sr.status == "pending"
        assert sr.pr_id == ""
        assert sr.tokens_used == 0
        assert not sr.critique_approved
        assert not sr.verification_passed
        assert sr.error == ""

    def test_sub_task_result_custom(self) -> None:
        """SubTaskResult 自定义值。"""
        sr = SubTaskResult(
            task_id="t1",
            status="ok",
            pr_id="pr-42",
            branch="feat/x",
            merge_sha="abc123",
            tokens_used=10_000,
            critique_approved=True,
            verification_passed=True,
        )
        assert sr.status == "ok"
        assert sr.merge_sha == "abc123"
        assert sr.tokens_used == 10_000

    def test_dep_edge_defaults(self) -> None:
        """DepEdge 默认值。"""
        de = DepEdge(from_id="g1", to_id="g2")
        assert de.type == "explicit"
        assert de.source == ""
        assert de.confidence == 1.0

    def test_dep_edge_implicit(self) -> None:
        """DepEdge 隐式依赖。"""
        de = DepEdge(from_id="g1", to_id="g2", type="implicit", source="LLM推断", confidence=0.6)
        assert de.confidence == 0.6
        assert de.type == "implicit"

    def test_dependency_conflict(self) -> None:
        """DependencyConflict。"""
        dc = DependencyConflict(type="cycle", goals=["g1", "g2"], suggestion="拆分PRD")
        assert dc.type == "cycle"
        assert dc.suggestion == "拆分PRD"

    def test_intake_decision_defaults(self) -> None:
        """IntakeDecision 默认值。"""
        dec = IntakeDecision()
        assert dec.needs_clarify
        assert dec.needs_decompose
        assert dec.clarity_score == 0.0
        assert dec.confidence == 0.5
        assert not dec.is_batch

    def test_goal_batch_report_defaults(self) -> None:
        """GoalBatchReport 默认值。"""
        br = GoalBatchReport()
        assert br.total_goals == 0
        assert br.completed == 0
        assert br.results == []


# =============================================================================
# 辅助: 同步运行 async 测试
# =============================================================================


def asyncio_run(coro):
    """同步 wrapper 运行 async 协程——sync 测试中无 running loop，直接 asyncio.run 即可。"""
    import asyncio

    return asyncio.run(coro)
