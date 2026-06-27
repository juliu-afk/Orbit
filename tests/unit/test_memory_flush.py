"""记忆刷新测试 (Phase 2 AC11a)."""

from __future__ import annotations

import pytest

from orbit.scheduler.flush import (
    MemoryFlushHandler,
    build_daily_log_entry,
    is_silent_turn,
)


class TestSilentTurnDetection:
    def test_empty_content_is_silent(self):
        msgs = [{"role": "assistant", "content": ""}]
        assert is_silent_turn(msgs)

    def test_ack_phrase_is_silent(self):
        msgs = [{"role": "assistant", "content": "ok"}]
        assert is_silent_turn(msgs)

    def test_tool_calls_not_silent(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "1", "type": "function", "function": {"name": "read_file"}}],
            }
        ]
        assert not is_silent_turn(msgs)

    def test_substantive_content_not_silent(self):
        msgs = [{"role": "assistant", "content": "Found a bug in auth.py line 42"}]
        assert not is_silent_turn(msgs)


class TestDailyLogEntry:
    def test_build_entry(self):
        entry = build_daily_log_entry(
            5,
            "task-001",
            "developer",
            [
                {"role": "assistant", "content": "ok"},
            ],
        )
        assert "task-001" in entry
        assert "developer" in entry
        assert "5" in entry


class TestMemoryFlushHandler:
    @pytest.mark.asyncio
    async def test_no_flush_on_active_turn(self):
        handler = MemoryFlushHandler()
        msgs = [{"role": "assistant", "content": "Found a bug in auth.py at line 42——needs fix"}]
        flushed = await handler.maybe_flush(1, "t1", "dev", msgs)
        assert not flushed
        assert handler.flush_count == 0

    @pytest.mark.asyncio
    async def test_flush_on_silent_turn(self):
        handler = MemoryFlushHandler()
        msgs = [{"role": "assistant", "content": ""}]
        flushed = await handler.maybe_flush(1, "t2", "dev", msgs)
        assert flushed
        assert handler.flush_count == 1
