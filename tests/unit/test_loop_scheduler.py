"""LoopScheduler 集成测试——CRUD + 状态机。

使用临时 SQLite DB 替代生产 DB_PATH，避免污染真实数据。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_db():
    """创建临时 SQLite DB，patch DB_PATH 为临时路径。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    try:
        os.unlink(path)
    except OSError:
        pass


class TestLoopSchedulerCRUD:
    """create / list / get / stop 生命周期。"""

    @pytest.mark.asyncio
    async def test_create_and_list(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            s = await scheduler.create("60", "echo test")
            assert s.interval_seconds == 60
            assert s.command == "echo test"
            assert s.status == "active"

            all_s = scheduler.list_all()
            assert len(all_s) >= 1

    @pytest.mark.asyncio
    async def test_get(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            s = await scheduler.create("120", "echo hello")
            found = scheduler.get(s.id)
            assert found is not None
            assert found.id == s.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            assert scheduler.get("nonexistent-id") is None

    @pytest.mark.asyncio
    async def test_create_max_limit(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            for i in range(scheduler.MAX_LOOPS):
                await scheduler.create("60", f"cmd_{i}")
            with pytest.raises(ValueError, match="max|上限"):
                await scheduler.create("60", "one_too_many")

    @pytest.mark.asyncio
    async def test_stop(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            s = await scheduler.create("60", "test")
            await scheduler.stop(s.id)
            stopped = scheduler.get(s.id)
            assert stopped is not None
            assert stopped.status == "stopped"

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            s = await scheduler.create("60", "test")
            await scheduler.pause(s.id)
            assert scheduler.get(s.id).status == "paused"
            await scheduler.resume(s.id)
            assert scheduler.get(s.id).status == "active"

    @pytest.mark.asyncio
    async def test_stop_nonexistent(self, temp_db):
        from orbit.loop.scheduler import LoopScheduler

        with patch("orbit.loop.scheduler.DB_PATH", temp_db):
            scheduler = LoopScheduler()
            # stop nonexistent should not raise (graceful no-op)
            await scheduler.stop("nonexistent-id")
