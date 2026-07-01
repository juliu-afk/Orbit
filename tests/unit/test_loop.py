"""Loop 调度器单元测试——CronParser/LoopSchedule/LoopRunner/LoopScheduler。

CronParser 纯逻辑，LoopSchedule Pydantic 校验，LoopScheduler 用 mock DB。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.loop.models import LoopSchedule, LoopRunner
from orbit.loop.parser import CronParser, CronParseError


class TestCronParser:
    """CronParser.parse()——纯逻辑，参数化覆盖所有输入格式。"""

    @pytest.mark.parametrize("expr,expected_secs", [
        # 纯数字（秒）
        ("60", 60),
        ("3600", 3600),
        ("1", 1),
        # 英文简写
        ("hourly", 3600),
        ("daily", 86400),
        ("weekly", 604800),
        # 数字+单位
        ("5m", 300),
        ("30m", 1800),
        ("2h", 7200),
        ("1d", 86400),
        ("7d", 604800),
        # 简单 5 字段 cron
        ("0 * * * *", 3600),
        ("*/5 * * * *", 300),
        ("*/15 * * * *", 900),
    ])
    def test_parse_valid_expressions(self, expr, expected_secs):
        parser = CronParser()
        result = parser.parse(expr)
        assert result == expected_secs, f"parse('{expr}') = {result}, expected {expected_secs}"

    @pytest.mark.parametrize("invalid_expr", [
        "",           # 空字符串
        "abc",        # 无意义文本
        "0 *",        # 不完整的 cron
        "0 * * *",    # 4 字段而非 5
        "-5m",        # 负数
        "0 * * * * *", # 6 字段
    ])
    def test_parse_invalid_raises(self, invalid_expr):
        parser = CronParser()
        with pytest.raises((CronParseError, ValueError)):
            parser.parse(invalid_expr)


class TestLoopScheduleModel:
    """LoopSchedule Pydantic 校验。"""

    def test_valid_schedule(self):
        s = LoopSchedule(interval_seconds=60, command="echo hello")
        assert s.interval_seconds == 60
        assert s.command == "echo hello"
        assert s.status == "active"
        assert s.run_count == 0
        assert s.id  # 自动生成

    def test_negative_interval_rejected(self):
        with pytest.raises(Exception):  # Pydantic validation
            LoopSchedule(interval_seconds=-1, command="test")

    def test_zero_interval_rejected(self):
        with pytest.raises(Exception):
            LoopSchedule(interval_seconds=0, command="test")

    def test_empty_command_rejected(self):
        with pytest.raises(Exception):
            LoopSchedule(interval_seconds=60, command="")

    def test_status_literal(self):
        s = LoopSchedule(interval_seconds=60, command="test", status="paused")
        assert s.status == "paused"

        s2 = LoopSchedule(interval_seconds=60, command="test", status="stopped")
        assert s2.status == "stopped"


class TestLoopRunner:
    """LoopRunner.run()——async 循环，用 Mock callback。"""

    @pytest.mark.asyncio
    async def test_runner_calls_callback(self):
        schedule = LoopSchedule(interval_seconds=1, command="test")
        call_count = 0

        async def callback(cmd):
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        runner = LoopRunner(schedule, callback)
        # 手动启动一轮后停止（避免无限循环）
        runner._running = True
        # 创建一个 task，跑 0.2s 后停止
        async def _run_then_stop():
            task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.3)
            runner.stop()
            await task

        await _run_then_stop()
        assert call_count >= 1
        assert schedule.status == "stopped"

    @pytest.mark.asyncio
    async def test_runner_catches_callback_exception(self):
        schedule = LoopSchedule(interval_seconds=1, command="failing")

        async def failing_callback(cmd):
            raise RuntimeError("boom")

        runner = LoopRunner(schedule, failing_callback)
        runner._running = True

        async def _run_then_stop():
            task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.3)
            runner.stop()
            await task

        # 不应崩溃
        await _run_then_stop()
        # 应记录失败但继续
        assert schedule.last_result is not None

    @pytest.mark.asyncio
    async def test_runner_calls_persist(self):
        schedule = LoopSchedule(interval_seconds=1, command="test")
        persist_called = []

        async def callback(cmd):
            return {"status": "ok"}

        def persist():
            """生产代码调用 _persist() 无参数。"""
            persist_called.append(1)

        runner = LoopRunner(schedule, callback, _persist=persist)
        runner._running = True

        async def _run_then_stop():
            task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.3)
            runner.stop()
            await task

        await _run_then_stop()
        assert len(persist_called) >= 1
