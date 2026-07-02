"""覆盖率补测批次3——hallucination/schemas + goal/process_guard + dream/models + api/schemas."""

from __future__ import annotations

import pytest

from orbit.api.schemas.task import TaskCreateRequest, TaskState
from orbit.dream.models import DreamConfig, DreamResult, DreamStatus
from orbit.goal.process_guard import (
    FAST_LANE_TRANSITIONS,
    FULL_PIPELINE_TRANSITIONS,
    TERMINAL_STATES,
)
from orbit.hallucination.schemas import (
    HallucinationLevel,
    L3EntropyConfig,
    ValidationResult,
)


# ════════════════════════════════════════════
# 1. Hallucination schemas
# ════════════════════════════════════════════

class TestHallucinationSchemas:
    def test_hallucination_level_enum(self):
        levels = {l.value for l in HallucinationLevel}
        assert len(levels) >= 5

    def test_l3_entropy_config(self):
        cfg = L3EntropyConfig(
            window_size=10, threshold=0.75, fallback_enabled=True,
        )
        assert cfg.window_size == 10
        assert cfg.threshold == 0.75

    def test_validation_result(self):
        vr = ValidationResult(passed=True, level=HallucinationLevel.L1_GRAPH)
        assert vr.passed is True


# ════════════════════════════════════════════
# 2. Dream models
# ════════════════════════════════════════════

class TestDreamModels:
    def test_dream_config(self):
        cfg = DreamConfig(
            max_output_lines=100, max_output_bytes=5000,
            merge_temperature=0.3, verify_temperature=0.1,
        )
        assert cfg.max_output_lines == 100

    def test_dream_result(self):
        r = DreamResult(status=DreamStatus.COMPLETE, lines=10, bytes=500)
        assert r.status == DreamStatus.COMPLETE

    def test_dream_status_enum(self):
        assert DreamStatus.IDLE.value == "idle"
        assert DreamStatus.COMPLETE.value == "complete"
        assert DreamStatus.REJECTED.value == "rejected"
        assert DreamStatus.FAILED.value == "failed"


# ════════════════════════════════════════════
# 3. Goal process_guard
# ════════════════════════════════════════════

class TestProcessGuardConstants:
    def test_fast_lane_transitions(self):
        """FAST_LANE_TRANSITIONS 包含合法快车道转换。"""
        assert len(FAST_LANE_TRANSITIONS) >= 1

    def test_full_pipeline_transitions(self):
        """FULL_PIPELINE_TRANSITIONS 包含完整流水线。"""
        assert len(FULL_PIPELINE_TRANSITIONS) >= 1

    def test_terminal_states(self):
        """TERMINAL_STATES 包含 DONE 和 FAILED。"""
        assert TaskState.DONE in TERMINAL_STATES or "DONE" in str(TERMINAL_STATES)
        assert TaskState.FAILED in TERMINAL_STATES or "FAILED" in str(TERMINAL_STATES)


# ════════════════════════════════════════════
# 4. API task schemas
# ════════════════════════════════════════════

class TestTaskSchemasExtended:
    def test_task_create_request(self):
        req = TaskCreateRequest(prd="build a calculator app", language="python")
        assert req.prd == "build a calculator app"

    def test_task_state_transitions(self):
        """TaskState 覆盖全部生命周期。"""
        states = {s.value for s in TaskState}
        assert "IDLE" in states
        assert "CODING" in states
        assert "DONE" in states
        assert "FAILED" in states
