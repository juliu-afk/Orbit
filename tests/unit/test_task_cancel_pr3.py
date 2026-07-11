"""PR3 回归：tasks 桩变真——Scheduler 取消机制 + 真实检查点状态。"""

from __future__ import annotations

import asyncio

import pytest

from orbit.checkpoint.manager import CheckpointData, CheckpointManager
from orbit.scheduler.orchestrator import Scheduler


@pytest.fixture
def scheduler():
    # 内存模式 checkpoint（无 Redis），最小 Scheduler
    cm = CheckpointManager(redis_client=None)
    return Scheduler(checkpoint_manager=cm)


@pytest.mark.asyncio
async def test_cancel_task_writes_cancelled_and_stops(scheduler):
    """cancel_task 取消运行中任务 + 写 CANCELLED 检查点 + 清理注册表。"""
    cm = scheduler.checkpoint
    await cm.save("t1", CheckpointData(task_id="t1", state="PARSING", progress=0.3))

    async def _long():
        await asyncio.sleep(100)

    running = asyncio.create_task(_long())
    scheduler._active_tasks["t1"] = running

    ok = await scheduler.cancel_task("t1")
    assert ok is True
    # 注册表已清理
    assert "t1" not in scheduler._active_tasks
    # 底层 asyncio 任务被取消
    await asyncio.sleep(0)
    assert running.cancelled() or running.done()
    # CANCELLED 检查点已写，且 version 递增（乐观锁）
    ckpt = await cm.load("t1")
    assert ckpt.state == "CANCELLED"
    assert ckpt.progress == 0.3  # 保留原进度
    assert ckpt.version == 2  # 原 version 1 + 1


@pytest.mark.asyncio
async def test_cancel_task_no_prior_checkpoint(scheduler):
    """无前置检查点时取消——仍写 CANCELLED（version=1）。"""
    ok = await scheduler.cancel_task("ghost")
    assert ok is True
    ckpt = await scheduler.checkpoint.load("ghost")
    assert ckpt.state == "CANCELLED"
    assert ckpt.version == 1


@pytest.mark.asyncio
async def test_spawn_task_registers_and_cleans_up(scheduler):
    """spawn_task 登记到注册表，完成后自动清理。"""
    # 用 monkeypatch 替换 run_task 为快速完成的假任务
    async def _fast(task_id, prd):
        return None

    scheduler.run_task = _fast  # type: ignore[method-assign]
    task = scheduler.spawn_task("s1", "prd text")
    assert "s1" in scheduler._active_tasks
    await task
    await asyncio.sleep(0)  # 让 done_callback 执行
    assert "s1" not in scheduler._active_tasks


@pytest.mark.asyncio
async def test_spawn_task_duplicate_returns_existing(scheduler):
    """P1-1: 同 task_id 重复 spawn 返回现有运行中任务，不污染注册表。"""
    async def _long(task_id, prd):
        await asyncio.sleep(100)

    scheduler.run_task = _long  # type: ignore[method-assign]
    t1 = scheduler.spawn_task("dup", "prd")
    t2 = scheduler.spawn_task("dup", "prd")  # 同 id 重复
    assert t1 is t2  # 返回同一任务，未新建
    assert scheduler._active_tasks["dup"] is t1
    t1.cancel()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_task_records_eviction_protects_running(scheduler, monkeypatch):
    """P2-5: 记录淘汰跳过运行中任务，保护其 prd/元数据不被误删。"""
    import orbit.api.routes.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "_MAX_TASK_RECORDS", 2)
    tasks_mod._task_records.clear()

    # 造 1 个运行中任务(在 _active_tasks) + 记录
    async def _long(task_id, prd):
        await asyncio.sleep(100)

    scheduler.run_task = _long  # type: ignore[method-assign]
    running_id = await tasks_mod.create_task_record(scheduler, "running prd")
    scheduler.spawn_task(running_id, "running prd")  # 登记到 _active_tasks

    # 再建 2 个记录触发淘汰——运行中的那个必须存活
    await tasks_mod.create_task_record(scheduler, "prd2")
    await tasks_mod.create_task_record(scheduler, "prd3")

    assert running_id in tasks_mod._task_records  # 运行中任务未被淘汰
    assert tasks_mod._task_records[running_id]["prd"] == "running prd"
    scheduler._active_tasks[running_id].cancel()
    await asyncio.sleep(0)
    tasks_mod._task_records.clear()
