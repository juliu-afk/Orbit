"""VIGIL shadow mode 单元测试——规则诊断 + 因果诊断集成."""

import pytest

from orbit.metacognition.vigil import (
    DiagnosisResult,
    FailureType,
    VigilSelfHealer,
)


class TestVigilShadowMode:
    """diagnose_with_causal() shadow mode——规则/因果并行对比."""

    def test_shadow_no_causal_analyzer(self):
        """无因果分析器时只返回规则结果."""
        import asyncio

        healer = VigilSelfHealer()
        result = asyncio.run(
            healer.diagnose_with_causal(
                task_id="t1", error_text="SyntaxError: invalid syntax",
                causal_analyzer=None,
            )
        )
        assert result["rule"] is not None
        assert result["causal"] is None
        assert result["winner"] == "rule"

    def test_shadow_rule_wins_by_confidence(self):
        """规则诊断置信度高 → rule 胜出."""
        import asyncio

        class MockAnalyzer:
            async def analyze(self, task_id):
                from orbit.causal.models import CauseCandidate, RootCause
                c = CauseCandidate(variable="agent_role", anomaly_score=0.30)
                return RootCause(task_id=task_id, causes=[c], top_cause=c,
                                 confidence=0.55)

        healer = VigilSelfHealer()
        # 规则模式下 SyntaxError 的 diagnose() 返回 confidence=0.85
        result = asyncio.run(
            healer.diagnose_with_causal(
                task_id="t1", error_text="SyntaxError: invalid syntax",
                causal_analyzer=MockAnalyzer(),
            )
        )
        assert result["rule"] is not None
        assert result["causal"] is not None
        # 规则 confidence=0.85 > 因果 0.55 → rule wins
        assert result["winner"] == "rule"

    def test_shadow_causal_wins_by_confidence(self):
        """因果诊断置信度显著高（差值 >= 0.1）→ causal 胜出."""
        import asyncio

        class MockAnalyzer:
            async def analyze(self, task_id):
                from orbit.causal.models import CauseCandidate, RootCause
                c = CauseCandidate(variable="agent_role", anomaly_score=0.80)
                return RootCause(task_id=task_id, causes=[c], top_cause=c,
                                 confidence=0.96)  # 0.96 - 0.85 = 0.11 >= 0.1

        healer = VigilSelfHealer()
        result = asyncio.run(
            healer.diagnose_with_causal(
                task_id="t1", error_text="SyntaxError: invalid syntax",
                causal_analyzer=MockAnalyzer(),
            )
        )
        assert result["causal"] is not None
        # |0.96 - 0.85| = 0.11 >= 0.1 → causal wins (not tie)
        assert result["winner"] == "causal"

    def test_shadow_tie_detection(self):
        """差值 <0.1 → tie——验证 P0 修复."""
        import asyncio

        class MockAnalyzer:
            async def analyze(self, task_id):
                from orbit.causal.models import CauseCandidate, RootCause
                c = CauseCandidate(variable="model_tier", anomaly_score=0.50)
                # 因果 confidence=0.83——与规则 0.85 差 0.02 < 0.1 → tie
                return RootCause(task_id=task_id, causes=[c], top_cause=c,
                                 confidence=0.83)

        healer = VigilSelfHealer()
        result = asyncio.run(
            healer.diagnose_with_causal(
                task_id="t1", error_text="SyntaxError: invalid syntax",
                causal_analyzer=MockAnalyzer(),
            )
        )
        # 差值 = |0.83 - 0.85| = 0.02 < 0.1 → tie
        assert result["winner"] == "tie"

    def test_shadow_low_causal_confidence_returns_none(self):
        """因果置信度 <0.3 → _diagnose_causal 返回 None."""
        import asyncio

        class MockAnalyzer:
            async def analyze(self, task_id):
                from orbit.causal.models import CauseCandidate, RootCause
                c = CauseCandidate(variable="agent_role", anomaly_score=0.10)
                return RootCause(task_id=task_id, causes=[c], top_cause=c,
                                 confidence=0.15)

        healer = VigilSelfHealer()
        result = asyncio.run(
            healer.diagnose_with_causal(
                task_id="t1", error_text="SyntaxError: invalid syntax",
                causal_analyzer=MockAnalyzer(),
            )
        )
        assert result["causal"] is None
        assert result["winner"] == "rule"
