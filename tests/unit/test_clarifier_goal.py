import pytest
from unittest.mock import MagicMock
class TestClarifierAgent:
    def test_init(self):
        from orbit.agents.clarifier.agent import ClarifierAgent
        assert ClarifierAgent(llm=MagicMock()) is not None
class TestGoalModels:
    def test_fields(self):
        from orbit.goal.models import GoalSession
        g = GoalSession(description="test", target_provider="deepseek")
        assert g.target_provider=="deepseek"
class TestReviewModels:
    def test_decision(self):
        from orbit.review.models import ReviewDecision
        d = ReviewDecision(status="approved", reason="ok")
        assert d.status=="approved"
