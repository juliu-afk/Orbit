"""Step 2.2 CheckpointManager 测试。

覆盖 PRD 验收标准：
- SC1: save 延迟（内存模式忽略，测功能）
- SC2: save 后 load 完整性 100%
- SC3: Redis 不可用降级 PG（用内存 mock PG）
- SC4: 版本号乐观锁防覆盖
"""
from __future__ import annotations

import pytest

from orbit.checkpoint.manager import (
    CheckpointCorruptedError,
    CheckpointData,
    CheckpointManager,
)


# ---- 内存 mock：Redis / PG 行为 ----


class FakeRedis:
    """内存 Redis mock，支持 setex/get + 模拟故障。"""

    def __init__(self, fail: bool = False):
        self.store: dict[str, bytes] = {}
        self.fail = fail

    async def setex(self, key, ttl, val):
        if self.fail:
            raise ConnectionError("Redis 不可用")
        self.store[key] = val

    async def get(self, key):
        if self.fail:
            raise ConnectionError("Redis 不可用")
        return self.store.get(key)


class FakePG:
    """内存 PG mock，支持 upsert + version 乐观锁。"""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    async def execute(self, query, *args):
        # DELETE 语句：args=(days,)，仅返回删除计数（mock 返回 0）
        if "DELETE" in query:
            return "DELETE 0"
        # INSERT/UPDATE：args=(task_id, state, retry, progress, ctx, ts, version)
        task_id = args[0]
        new_version = args[6]
        existing = self.rows.get(task_id)
        # 模拟 ON CONFLICT WHERE version <= EXCLUDED.version
        if existing and existing["version"] > new_version:
            return "UPDATE 0"  # 旧版本不覆盖
        self.rows[task_id] = {
            "state": args[1],
            "retry_count": args[2],
            "progress": args[3],
            "context": args[4],
            "updated_at": args[5],
            "version": (existing["version"] + 1 if existing else new_version),
        }
        return "INSERT 0 1" if not existing else "UPDATE 1"

    async def fetchrow(self, query, task_id):
        row = self.rows.get(task_id)
        return row


# ---- fixtures ----


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def fake_pg():
    return FakePG()


@pytest.fixture
def mgr(fake_redis, fake_pg):
    return CheckpointManager(
        redis_client=fake_redis, pg_pool=fake_pg, env="test"
    )


# ---- 测试 ----


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(mgr):
    """SC2: save 后 load 完整恢复。"""
    data = CheckpointData(
        task_id="task-1",
        state="CODING",
        retry_count=0,
        progress=0.5,
        context={"code": "print('hi')", "files": ["a.py"]},
    )
    await mgr.save("task-1", data)
    loaded = await mgr.load("task-1")
    assert loaded is not None
    assert loaded.task_id == "task-1"
    assert loaded.state == "CODING"
    assert loaded.progress == 0.5
    assert loaded.context["code"] == "print('hi')"
    assert loaded.context["files"] == ["a.py"]


@pytest.mark.asyncio
async def test_redis_miss_fallback_pg(mgr, fake_redis, fake_pg):
    """SC3: Redis miss 时从 PG 读取并回填。

    WHY 直接 await _save_to_pg：save() 的 PG 写是 fire-and-forget，
    真实场景 PG 早已写完（崩溃后重启）。测试用同步写模拟"PG 已有数据"。
    """
    data = CheckpointData(task_id="task-2", state="PLANNING")
    await mgr._save_to_pg("task-2", data, b"{}")
    # 清 Redis，模拟 miss
    fake_redis.store.clear()
    loaded = await mgr.load("task-2")
    assert loaded is not None
    assert loaded.state == "PLANNING"
    # 回填后 Redis 应有
    assert any("task-2" in k for k in fake_redis.store)


@pytest.mark.asyncio
async def test_redis_failure_degrades_to_pg(mgr, fake_redis):
    """SC3: Redis 故障时仍能写 PG + 从 PG 读。"""
    data = CheckpointData(task_id="task-3", state="CODING")
    # 让 Redis 写失败
    fake_redis.fail = True
    await mgr.save("task-3", data)  # 不应抛异常
    # Redis 读也失败，降级到 PG
    loaded = await mgr.load("task-3")
    assert loaded is not None
    assert loaded.state == "CODING"


@pytest.mark.asyncio
async def test_version_optimistic_lock(mgr, fake_pg):
    """SC4: 旧版本不覆盖新版本。"""
    v1 = CheckpointData(task_id="task-4", state="PLANNING", version=1)
    v2 = CheckpointData(task_id="task-4", state="CODING", version=2)
    await mgr._save_to_pg("task-4", v1, b"{}")
    await mgr._save_to_pg("task-4", v2, b"{}")
    # PG 现在应该是 version=3（INSERT v1 → UPDATE v2 version+1）
    loaded = await mgr._load_from_pg("task-4")
    assert loaded.version >= 2
    assert loaded.state == "CODING"


@pytest.mark.asyncio
async def test_version_old_does_not_overwrite(mgr, fake_pg):
    """SC4 补充：版本号小的晚到不覆盖大的。"""
    v2 = CheckpointData(task_id="task-5", state="CODING", version=2)
    v1 = CheckpointData(task_id="task-5", state="PLANNING", version=1)
    await mgr._save_to_pg("task-5", v2, b"{}")
    # v1 晚到（version 小），不应覆盖 v2
    await mgr._save_to_pg("task-5", v1, b"{}")
    loaded = await mgr._load_from_pg("task-5")
    assert loaded.state == "CODING"  # 保持新版本的状态


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none(mgr):
    """加载不存在的任务返回 None（不抛异常）。"""
    loaded = await mgr.load("nonexistent-task")
    assert loaded is None


@pytest.mark.asyncio
async def test_memory_only_mode():
    """无 Redis 无 PG 时纯内存模式。"""
    mgr = CheckpointManager(redis_client=None, pg_pool=None, env="mem")
    data = CheckpointData(task_id="task-mem", state="IDLE")
    await mgr.save("task-mem", data)
    loaded = await mgr.load("task-mem")
    assert loaded is not None
    assert loaded.state == "IDLE"


@pytest.mark.asyncio
async def test_cleanup_calls_pg(fake_pg):
    """cleanup_old_checkpoints 调用 PG。"""
    mgr = CheckpointManager(redis_client=None, pg_pool=fake_pg, env="clean")
    # FakePG.execute 不处理 DELETE，返回 None，方法返回 0
    result = await mgr.cleanup_old_checkpoints(days=7)
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_checkpoint_data_defaults():
    """CheckpointData 默认值校验（state 必填，其余有默认）。"""
    data = CheckpointData(task_id="t", state="IDLE")
    assert data.version == 1
    assert data.progress == 0.0
    assert data.context == {}
    assert data.state == "IDLE"


@pytest.mark.asyncio
async def test_progress_validation():
    """progress 超出范围抛 ValidationError。"""
    with pytest.raises(Exception):
        CheckpointData(task_id="t", state="X", progress=1.5)
    with pytest.raises(Exception):
        CheckpointData(task_id="t", state="X", progress=-0.1)


@pytest.mark.asyncio
async def test_version_validation():
    """version < 1 抛 ValidationError。"""
    with pytest.raises(Exception):
        CheckpointData(task_id="t", state="X", version=0)
