"""Scheduler extended tests — task_runner/context + checkpoint + complexity.
Coverage sprint 8: target scheduler/ modules.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.scheduler.complexity import ComplexityScorer
from orbit.scheduler.task_runner.checkpoint import _state_to_progress, _transition
from orbit.api.schemas.task import TaskState


class TestComplexityScorer:
    def test_init(self):
        s = ComplexityScorer()
        assert s is not None

    def test_score_empty_task(self):
        s = ComplexityScorer()
        score = s.score("")
        assert 0 <= score <= 100

    def test_score_simple_task(self):
        s = ComplexityScorer()
        score = s.score("fix typo in README")
        assert score < 50

    def test_score_complex_task(self):
        s = ComplexityScorer()
        score = s.score("Implement distributed transaction with 2PC across microservices with PostgreSQL and Redis")
        assert score > 50


class TestStateTransitions:
    def test_state_to_progress(self):
        for state in TaskState:
            pct = _state_to_progress(state)
            assert 0 <= pct <= 100

    def test_transition_valid(self):
        t = _transition(TaskState.PLANNING, TaskState.CODING)
        assert t is True

    def test_transition_invalid(self):
        t = _transition(TaskState.IDLE, TaskState.VERIFYING)
        assert t is False

    def test_all_states_have_progress(self):
        """All states have progress values."""
        states_with_progress = {
            TaskState.IDLE, TaskState.PARSING, TaskState.SCOPING,
            TaskState.PLANNING, TaskState.CODING, TaskState.VERIFYING,
        }
        for state in states_with_progress:
            pct = _state_to_progress(state)
            assert isinstance(pct, (int, float))
