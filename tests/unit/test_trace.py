"""TraceSpan/TraceCollector/TraceStore 单元测试（Inkeep 借鉴 #4）。

覆盖: span 创建/结束/树构建/序列化/导出/清理。
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import pytest


class TestTraceSpan:
    """TraceSpan 数据模型。"""

    def test_span_creation(self):
        from orbit.observability.trace import SpanStatus, TraceSpan

        span = TraceSpan(
            task_id="task-1",
            component="orchestrator",
            action="schedule",
            input_summary="调度决策",
        )
        assert span.span_id  # 自动生成
        assert span.task_id == "task-1"
        assert span.component == "orchestrator"
        assert span.status == SpanStatus.IN_PROGRESS

    def test_span_serialization(self):
        from orbit.observability.trace import TraceSpan

        span = TraceSpan(
            span_id="abc123",
            task_id="task-1",
            component="agent",
            action="agent_call",
            duration_ms=150.0,
        )
        dumped = span.model_dump()
        assert dumped["span_id"] == "abc123"
        assert dumped["duration_ms"] == 150.0

    def test_span_metadata(self):
        from orbit.observability.trace import TraceSpan

        span = TraceSpan(
            task_id="task-1",
            component="tool",
            action="tool_exec",
            metadata={"tool_name": "load_knowledge", "token_count": 42},
        )
        assert span.metadata["tool_name"] == "load_knowledge"


class TestTraceCollector:
    """TraceCollector 异步 span 收集。"""

    def test_start_span(self):
        from orbit.observability.trace import SpanStatus, TraceCollector

        span = TraceCollector.start_span(
            "task-1", component="agent", action="agent_call"
        )
        assert span.status == SpanStatus.IN_PROGRESS
        assert span.component == "agent"

    def test_end_span(self):
        from orbit.observability.trace import SpanStatus, TraceCollector

        span = TraceCollector.start_span("task-1", component="sandbox", action="tool_exec")
        TraceCollector.end_span(span, status=SpanStatus.OK, output_summary="执行成功")
        assert span.status == SpanStatus.OK
        assert span.output_summary == "执行成功"

    def test_input_truncated(self):
        from orbit.observability.trace import TraceCollector

        long_input = "A" * 500
        span = TraceCollector.start_span(
            "task-1", component="agent", action="agent_call", input_summary=long_input
        )
        assert len(span.input_summary) <= 256

    def test_parent_span_id(self):
        from orbit.observability.trace import TraceCollector

        root = TraceCollector.start_span("task-1", component="orchestrator", action="schedule")
        child = TraceCollector.start_span(
            "task-1", component="agent", action="agent_call",
            parent_span_id=root.span_id,
        )
        assert child.parent_span_id == root.span_id


@pytest.mark.asyncio
class TestTraceStoreAsync:
    """TraceStore 异步查询——直接写入 SQLite 验证查询逻辑。"""

    async def test_empty_trace(self):
        """不存在的 task 返回 None。"""
        from orbit.observability.trace import TraceStore

        store = TraceStore(":memory:")
        tree = await store.get_trace_tree("nonexistent-task")
        assert tree is None

    async def test_tree_builds_from_spans(self):
        """手动插入 span 数据后构建 tree。"""
        import aiosqlite

        from orbit.observability.trace import TraceStore

        db_path = tempfile.mktemp(suffix=".db")
        try:
            # 创建表
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS trace_spans (
                        span_id TEXT PRIMARY KEY,
                        parent_span_id TEXT,
                        task_id TEXT NOT NULL,
                        component TEXT NOT NULL,
                        action TEXT NOT NULL,
                        input_summary TEXT DEFAULT '',
                        output_summary TEXT DEFAULT '',
                        duration_ms REAL DEFAULT 0,
                        status TEXT DEFAULT 'in_progress',
                        created_at TEXT NOT NULL,
                        metadata_json TEXT DEFAULT '{}'
                    )"""
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_task_id ON trace_spans(task_id)"
                )
                await db.execute(
                    """INSERT INTO trace_spans VALUES
                       ('s1', NULL, 'task-1', 'orchestrator', 'schedule',
                        '', '', 50.0, 'ok', '2026-01-01T00:00:00', '{}'),
                       ('s2', 's1', 'task-1', 'agent', 'agent_call',
                        '', '', 100.0, 'ok', '2026-01-01T00:00:01', '{}')"""
                )
                await db.commit()

            store = TraceStore(db_path)
            tree = await store.get_trace_tree("task-1")
            assert tree is not None
            assert tree.task_id == "task-1"
            assert tree.span_count == 2
            assert tree.total_duration_ms == 50.0  # root spans only
            assert len(tree.root_spans) == 1
            assert tree.root_spans[0].span_id == "s1"
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestTraceTree:
    """TraceTree 数据模型。"""

    def test_tree_serialization(self):
        from orbit.observability.trace import SpanStatus, TraceSpan, TraceTree

        tree = TraceTree(
            task_id="task-1",
            root_spans=[
                TraceSpan(
                    span_id="root1",
                    task_id="task-1",
                    component="orchestrator",
                    action="schedule",
                    status=SpanStatus.OK,
                    duration_ms=100.0,
                ),
            ],
            total_duration_ms=100.0,
            span_count=1,
        )
        dumped = tree.model_dump()
        assert dumped["task_id"] == "task-1"
        assert dumped["span_count"] == 1
        json.dumps(dumped)  # 可序列化


class TestSpanStatus:
    """SpanStatus 枚举。"""

    def test_status_values(self):
        from orbit.observability.trace import SpanStatus

        assert SpanStatus.OK == "ok"
        assert SpanStatus.ERROR == "error"
        assert SpanStatus.TIMEOUT == "timeout"
        assert SpanStatus.IN_PROGRESS == "in_progress"
