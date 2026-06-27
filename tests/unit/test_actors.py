"""Actor 子系统单元测试——Registry + Spawn + Watchdog.

Phase 3 组 2 (AC14): 覆盖 SQLite 状态机、子Agent 创建、stale 检测。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def temp_db():
    """临时 SQLite 数据库——用 :memory: 避免 Windows 文件锁问题。"""
    yield Path(":memory:")


class TestActorRegistry:
    """ActorRegistry——SQLite 状态机。"""

    def test_register_and_get(self, temp_db):
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        record = ActorRecord(
            actor_id="act-001",
            parent_task_id="task-001",
            role="developer",
            task="write tests",
        )
        reg.register(record)

        found = reg.get("act-001")
        assert found is not None
        assert found.actor_id == "act-001"
        assert found.status == ActorStatus.PENDING
        assert found.role == "developer"

    def test_get_nonexistent(self, temp_db):
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        assert reg.get("nonexistent") is None

    def test_update_status(self, temp_db):
        from orbit.actors.models import ActorOutcome, ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        reg.register(ActorRecord(actor_id="act-002", task="test"))

        reg.update_status("act-002", ActorStatus.RUNNING)
        found = reg.get("act-002")
        assert found.status == ActorStatus.RUNNING

        reg.update_status(
            "act-002",
            ActorStatus.IDLE,
            outcome=ActorOutcome.SUCCESS,
            result={"output": "done"},
        )
        found = reg.get("act-002")
        assert found.status == ActorStatus.IDLE
        assert found.outcome == ActorOutcome.SUCCESS
        assert found.result == {"output": "done"}

    def test_get_by_parent(self, temp_db):
        from orbit.actors.models import ActorRecord
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        reg.register(ActorRecord(actor_id="a1", parent_task_id="p1", task="t1"))
        reg.register(ActorRecord(actor_id="a2", parent_task_id="p1", task="t2"))
        reg.register(ActorRecord(actor_id="a3", parent_task_id="p2", task="t3"))

        children = reg.get_by_parent("p1")
        assert len(children) == 2
        assert {c.actor_id for c in children} == {"a1", "a2"}

    def test_count_active(self, temp_db):
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        reg.register(ActorRecord(actor_id="a1", task="t1"))
        reg.register(ActorRecord(actor_id="a2", task="t2"))

        assert reg.count_active() == 2  # both pending

        reg.update_status("a1", ActorStatus.IDLE)
        assert reg.count_active() == 1  # only a2 still pending

    def test_list_active(self, temp_db):
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        reg.register(ActorRecord(actor_id="a1", task="t1"))
        reg.register(ActorRecord(actor_id="a2", task="t2"))
        reg.update_status("a1", ActorStatus.RUNNING)
        reg.update_status("a2", ActorStatus.IDLE)

        active = reg.list_active()
        assert len(active) == 1
        assert active[0].actor_id == "a1"

    def test_allocate_unique_ids(self, temp_db):
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        ids = {reg.allocate() for _ in range(100)}
        assert len(ids) == 100  # all unique

    def test_mark_zombie_and_delete(self, temp_db):
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)
        reg.register(ActorRecord(actor_id="z1", task="stale task"))
        reg.mark_zombie("z1")
        found = reg.get("z1")
        assert found.status == ActorStatus.ZOMBIE

        reg.delete("z1")
        assert reg.get("z1") is None


class TestActorSpawn:
    """ActorSpawn——子Agent 创建。"""

    @pytest.mark.asyncio
    async def test_spawn_completes(self, temp_db):
        """基本 spawn 流程——Agent 完成任务。"""
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn

        reg = ActorRegistry(temp_db)
        spawn = ActorSpawn(registry=reg)

        deferred = await spawn.spawn(
            task="simple task",
            role="developer",
            parent_task_id="p1",
            background=False,
        )

        result = await deferred.result(timeout=5)
        assert result["status"] == "ok"
        assert deferred.done

        # 验证 registry 中状态已更新
        record = reg.get(deferred.actor_id)
        assert record.status.value == "idle"

    @pytest.mark.asyncio
    async def test_spawn_background(self, temp_db):
        """后台执行——Deferred 稍后查询。"""
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn

        reg = ActorRegistry(temp_db)
        spawn = ActorSpawn(registry=reg)

        deferred = await spawn.spawn(
            task="bg task",
            role="developer",
            parent_task_id="p1",
            background=True,
        )

        # 后台模式——Deferred 立即返回
        assert deferred.actor_id
        # 等待完成
        result = await deferred.result(timeout=5)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_spawn_concurrency_limit(self, temp_db):
        """并发限制——超过 MAX_CONCURRENT 抛出 RuntimeError。"""
        from orbit.actors.models import ActorRecord, ActorStatus
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn

        reg = ActorRegistry(temp_db)
        # 预填充 MAX_CONCURRENT 个 active actor
        for i in range(ActorRecord.MAX_CONCURRENT):
            reg.register(ActorRecord(actor_id=f"a{i}", task=f"t{i}", status=ActorStatus.RUNNING))

        spawn = ActorSpawn(registry=reg)
        with pytest.raises(RuntimeError, match="并发子Agent 已达上限"):
            await spawn.spawn(task="overflow", role="developer", background=False)

    @pytest.mark.asyncio
    async def test_deferred_cancel(self, temp_db):
        """取消子Agent——CancelledError 被捕获。"""
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.spawn import ActorSpawn

        reg = ActorRegistry(temp_db)
        spawn = ActorSpawn(registry=reg)

        deferred = await spawn.spawn(
            task="long task",
            role="developer",
            parent_task_id="p1",
            background=True,
        )
        deferred.cancel()
        # 取消后 deferred.done 为 True
        # 注意: result() 可能抛出 CancelledError——这是预期行为
        try:
            result = await deferred.result(timeout=5)
            assert "cancelled" in str(result).lower() or deferred.done
        except asyncio.CancelledError:
            pass  # 取消已生效


class TestActorWatchdog:
    """Watchdog——stale actor 检测。"""

    @pytest.mark.asyncio
    async def test_find_stale_actors(self, temp_db):
        """stale 检测——过去时间戳的记录被找到。"""
        from datetime import UTC, datetime, timedelta

        from orbit.actors.models import ActorRecord
        from orbit.actors.registry import ActorRegistry

        reg = ActorRegistry(temp_db)

        # 注册后手动设 updated_at 为 10 分钟前
        reg.register(ActorRecord(actor_id="old", task="old"))
        with reg._conn() as conn:
            old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            conn.execute(
                "UPDATE actor_registry SET updated_at = ? WHERE actor_id = ?",
                (old_time, "old"),
            )

        # stale_seconds=300（5分钟）——old actor 应被检测
        stale = reg.find_stale(stale_seconds=300)
        assert len(stale) >= 1

    @pytest.mark.asyncio
    async def test_watchdog_scan_and_cleanup(self, temp_db):
        """Watchdog 扫描 + 清理 zombie。"""
        from datetime import UTC, datetime, timedelta

        from orbit.actors.models import ActorRecord
        from orbit.actors.registry import ActorRegistry
        from orbit.actors.watchdog import ActorWatchdog

        reg = ActorRegistry(temp_db)
        reg.register(ActorRecord(actor_id="z1", task="stale"))
        # 手动设 updated_at 为 10 分钟前
        with reg._conn() as conn:
            old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            conn.execute(
                "UPDATE actor_registry SET updated_at = ? WHERE actor_id = ?",
                (old_time, "z1"),
            )

        watchdog = ActorWatchdog(reg, stale_seconds=300)
        await watchdog._scan()

        # zombie 被清理
        assert reg.get("z1") is None
