"""覆盖率补测——events/schemas.py, memory/models.py, goal_judge/models.py, api/schemas/task.py."""

from __future__ import annotations

import pytest

from orbit.api.schemas.task import HealthResponse, TaskState
from orbit.events.schemas import DashboardEvent
from orbit.goal_judge.models import Goal, JUDGE_SYSTEM_PROMPT, Verdict
from orbit.memory.models import (
    DecisionRecord,
    MemoryConfig,
    MemoryFile,
    MemoryFileType,
    MemorySearchQuery,
    MemorySearchResult,
)


# ════════════════════════════════════════════
# 1. events/schemas.py
# ════════════════════════════════════════════

class TestDashboardEvent:
    def test_basic_event(self):
        """DashboardEvent 基本构造。"""
        event = DashboardEvent(
            type="task:update",
            task_id="task-1",
            payload={"state": "DONE", "progress": 1.0},
        )
        assert event.type == "task:update"
        assert event.task_id == "task-1"
        assert event.payload["state"] == "DONE"

    def test_event_with_dag(self):
        """DashboardEvent 带 DAG 数据。"""
        event = DashboardEvent(
            type="task:update",
            task_id="task-2",
            payload={"state": "CODING", "dag": [{"id": "1", "name": "architect"}]},
        )
        assert len(event.payload["dag"]) == 1

    def test_event_with_timestamp(self):
        """DashboardEvent 自定义时间戳。"""
        event = DashboardEvent(
            type="agent:progress",
            task_id="t1",
            payload={"progress": 0.5, "agent_id": "dev-1"},
        )
        assert event.timestamp is not None
        assert event.payload["agent_id"] == "dev-1"


# ════════════════════════════════════════════
# 2. memory/models.py
# ════════════════════════════════════════════

class TestMemoryModels:
    def test_memory_file_type(self):
        """MemoryFileType 枚举值。"""
        assert MemoryFileType.EPISODIC.value == "MEMORY.md"
        assert MemoryFileType.NOTES.value == "notes.md"
        assert MemoryFileType.CHECKPOINT.value == "checkpoint.md"

    def test_memory_file_basic(self):
        """MemoryFile 基本构造。"""
        mem = MemoryFile(
            path="/tmp/test.md",
            file_type=MemoryFileType.EPISODIC,
            frontmatter={"type": "episodic", "updated": ""},
            body="# Section\ncontent here",
        )
        assert mem.body == "# Section\ncontent here"
        assert mem.frontmatter["type"] == "episodic"
        assert mem.path == "/tmp/test.md"

    def test_memory_search_query(self):
        """MemorySearchQuery 基本字段。"""
        q = MemorySearchQuery(query="test query", max_results=5)
        assert q.query == "test query"
        assert q.max_results == 5

    def test_memory_search_result(self):
        """MemorySearchResult 基本字段。"""
        r = MemorySearchResult(
            path="/tmp/memory.md", score=0.85, snippet="relevant snippet",
            line_number=10, entry_score=1.5,
        )
        assert r.path == "/tmp/memory.md"
        assert r.score == 0.85
        assert r.entry_score == 1.5

    def test_memory_config(self):
        """MemoryConfig 基本字段。"""
        c = MemoryConfig(
            project_root="/tmp/project",
            memory_dir=".orbit/memory",
            max_memory_file_size=50_000,
        )
        assert c.project_root == "/tmp/project"
        assert c.max_memory_file_size == 50_000

    def test_decision_record(self):
        """DecisionRecord 基本字段。"""
        dr = DecisionRecord(
            id="DD-20260702-001",
            choice="PostgreSQL over MySQL",
            why="better JSON support and scalability",
            constraints=["must support JSONB"],
            alternatives=["MySQL 8.0", "SQLite"],
        )
        assert dr.choice == "PostgreSQL over MySQL"
        assert len(dr.alternatives) == 2
        assert "JSONB" in dr.constraints[0]


# ════════════════════════════════════════════
# 3. goal_judge/models.py
# ════════════════════════════════════════════

class TestGoalJudgeModels:
    def test_verdict_ok(self):
        """Verdict——目标达成。"""
        v = Verdict(ok=True, reason="All tasks completed")
        assert v.ok is True
        assert v.reason == "All tasks completed"

    def test_verdict_not_ok(self):
        """Verdict——目标未达成，带建议。"""
        v = Verdict(
            ok=False,
            reason="Incomplete",
            suggestions=["Try different approach", "Check error logs"],
            impossible=False,
        )
        assert v.ok is False
        assert len(v.suggestions) == 2
        assert v.impossible is False

    def test_verdict_impossible(self):
        """Verdict——目标不可完成。"""
        v = Verdict(
            ok=False,
            impossible=True,
            reason="Cannot access required API",
        )
        assert v.impossible is True

    def test_goal_model(self):
        """Goal 基本字段。"""
        g = Goal(
            description="Build auth system",
            react_count=3,
        )
        assert g.description == "Build auth system"
        assert g.react_count == 3
        assert g.MAX_REACT == 12

    def test_judge_system_prompt_not_empty(self):
        """JUDGE_SYSTEM_PROMPT 非空。"""
        assert len(JUDGE_SYSTEM_PROMPT) > 50


# ════════════════════════════════════════════
# 4. api/schemas/task.py
# ════════════════════════════════════════════

class TestTaskSchemas:
    def test_task_state_enum(self):
        """TaskState 枚举包含全部状态。"""
        states = {s.value for s in TaskState}
        assert "IDLE" in states
        assert "DONE" in states
        assert "FAILED" in states

    def test_health_response_ok(self):
        """HealthResponse OK 状态。"""
        hr = HealthResponse(status="ok", version="1.0.0")
        assert hr.status == "ok"
        assert hr.version == "1.0.0"

    def test_health_response_degraded(self):
        """HealthResponse degraded 状态。"""
        hr = HealthResponse(status="degraded", version="0.11.0")
        assert hr.status == "degraded"
