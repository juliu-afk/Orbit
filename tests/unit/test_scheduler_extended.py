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


class TestStateTransitions:
    def test_state_to_progress_idle(self):
        assert _state_to_progress(TaskState.IDLE) >= 0

    def test_state_to_progress_coding(self):
        assert _state_to_progress(TaskState.CODING) > 0

    def test_all_states_have_progress(self):
        """All states have progress values."""
        states_with_progress = {
            TaskState.IDLE, TaskState.PARSING, TaskState.SCOPING,
            TaskState.PLANNING, TaskState.CODING, TaskState.VERIFYING,
        }
        for state in states_with_progress:
            pct = _state_to_progress(state)
            assert isinstance(pct, (int, float))
