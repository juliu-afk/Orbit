"""检查点持久化（Step 2.2）。

WHY 双层存储：Redis 存热数据（快速恢复，TTL 1h），PG 存冷备份（Redis 丢/重启不丢）。
加载路径：Redis → miss → PG → 回填 Redis。

调度器在每次状态转换后调用 save()，崩溃重启后调用 load() 恢复到断点。
"""
from __future__ import annotations

import time
from typing import Any

import orjson
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

CHECKPOINT_TTL = 3600  # Redis TTL（秒），PRD 环境配置 CHECKPOINT_TTL=3600


class CheckpointData(BaseModel):
    """检查点数据（序列化存 Redis/PG）。

    version 用于乐观锁：并发写入时旧版本不能覆盖新版本。
    """

    task_id: str
    state: str  # 调度器状态机当前状态
    retry_count: int = 0
    progress: float = Field(0.0, ge=0.0, le=1.0)
    context: dict[str, Any] = Field(default_factory=dict)
    updated_at: float = Field(default_factory=time.time)
    version: int = Field(1, ge=1)


class CheckpointError(Exception):
    """检查点操作基类异常。"""


class CheckpointNotFoundError(CheckpointError):
    """加载时未找到检查点。"""


class CheckpointCorruptedError(CheckpointError):
    """检查点数据损坏（反序列化失败）。"""


class CheckpointManager:
    """Redis（热）+ PG（冷）双层检查点存储。

    架构位置：基础设施层，被调度器 SchedulerStateMachine 依赖注入调用。
    设计依据：PRD Step 2.2。
    """

    def __init__(
        self,
        redis_client: Any | None = None,
        pg_pool: Any | None = None,
        env: str = "dev",
    ):
        """初始化。

        Args:
            redis_client: redis.asyncio.Redis 实例（None 时降级纯内存）
            pg_pool: asyncpg.Pool 或等价对象（None 时跳过 PG 备份）
            env: 环境标识，拼进 Redis key 前缀避免多环境数据混淆
        """
        self.redis = redis_client
        self.pg = pg_pool
        self.env = env
        self._key_prefix = f"ckpt:{env}"
        # 内存降级（Redis/PG 都不可用时用，仅单实例）
        self._memory_store: dict[str, bytes] = {}

    async def save(self, task_id: str, data: CheckpointData) -> None:
        """保存检查点（Redis 同步 + PG fire-and-forget）。

        Redis 写失败时重试一次，仍失败则降级内存模式（SC3 降级路径）。
        PG 写失败不影响主流程（fire-and-forget，仅记日志）。
        """
        serialized = orjson.dumps(data.model_dump())
        key = f"{self._key_prefix}:{task_id}"

        # 写 Redis（重试一次）
        await self._save_to_redis(key, serialized)
        # 异步写 PG（fire-and-forget）
        if self.pg is not None:
            import asyncio

            asyncio.create_task(self._save_to_pg(task_id, data, serialized))

    async def load(self, task_id: str) -> CheckpointData | None:
        """加载检查点。Redis → miss → PG → 回填 Redis → 都 miss → None。"""
        key = f"{self._key_prefix}:{task_id}"
        # 1. 读 Redis
        redis_data = await self._load_from_redis(key)
        if redis_data is not None:
            return self._deserialize(redis_data, task_id)
        # 2. 降级读 PG
        if self.pg is not None:
            pg_data = await self._load_from_pg(task_id)
            if pg_data is not None:
                # 回填 Redis
                await self._save_to_redis(key, orjson.dumps(pg_data.model_dump()))
                return pg_data
        # 3. 降级内存
        if key in self._memory_store:
            return self._deserialize(self._memory_store[key], task_id)
        return None

    async def cleanup_old_checkpoints(self, days: int = 7) -> int:
        """清理 PG 中过期检查点。返回删除行数。"""
        if self.pg is None:
            return 0
        query = "DELETE FROM checkpoints WHERE updated_at < NOW() - make_interval(days => $1)"
        result = await self.pg.execute(query, days)
        # asyncpg 返回 "DELETE N" 格式
        try:
            return int(str(result).split()[-1])
        except (IndexError, ValueError):
            return 0

    # ---- Redis 层 ----

    async def _save_to_redis(self, key: str, serialized: bytes) -> None:
        """写 Redis，失败重试一次，仍失败降级内存。"""
        if self.redis is None:
            self._memory_store[key] = serialized
            return
        try:
            await self.redis.setex(key, CHECKPOINT_TTL, serialized)
        except Exception as e:
            logger.warning("redis_save_retry", key=key, error=str(e))
            try:
                await self.redis.setex(key, CHECKPOINT_TTL, serialized)
            except Exception as e2:
                # 降级内存
                logger.error("redis_save_fallback_memory", key=key, error=str(e2))
                self._memory_store[key] = serialized

    async def _load_from_redis(self, key: str) -> bytes | None:
        if self.redis is None:
            return self._memory_store.get(key)
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.warning("redis_load_failed", key=key, error=str(e))
            return self._memory_store.get(key)

    # ---- PG 层 ----

    async def _save_to_pg(
        self, task_id: str, data: CheckpointData, serialized: bytes
    ) -> None:
        """写 PG，带版本号乐观锁（WHERE checkpoints.version < EXCLUDED.version）。

        fire-and-forget 调用，异常仅记 Critical 日志（不影响主流程）。
        """
        query = """
        INSERT INTO checkpoints (task_id, state, retry_count, progress, context, updated_at, version)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (task_id) DO UPDATE SET
            state = EXCLUDED.state,
            retry_count = EXCLUDED.retry_count,
            progress = EXCLUDED.progress,
            context = EXCLUDED.context,
            updated_at = EXCLUDED.updated_at,
            version = checkpoints.version + 1
        WHERE checkpoints.version < EXCLUDED.version
        """
        try:
            await self.pg.execute(
                query,
                task_id,
                data.state,
                data.retry_count,
                data.progress,
                orjson.dumps(data.context),
                data.updated_at,
                data.version,
            )
        except Exception as e:
            logger.error(
                "pg_save_failed_fire_and_forget",
                task_id=task_id,
                error=str(e),
            )

    async def _load_from_pg(self, task_id: str) -> CheckpointData | None:
        query = "SELECT state, retry_count, progress, context, updated_at, version FROM checkpoints WHERE task_id = $1"
        try:
            row = await self.pg.fetchrow(query, task_id)
        except Exception as e:
            logger.warning("pg_load_failed", task_id=task_id, error=str(e))
            return None
        if not row:
            return None
        return CheckpointData(
            task_id=task_id,
            state=row["state"],
            retry_count=row["retry_count"],
            progress=row["progress"],
            context=orjson.loads(row["context"]),
            updated_at=row["updated_at"],
            version=row["version"],
        )

    # ---- 序列化 ----

    @staticmethod
    def _deserialize(raw: bytes, task_id: str) -> CheckpointData:
        """反序列化，失败抛 CheckpointCorruptedError。"""
        try:
            return CheckpointData(**orjson.loads(raw))
        except Exception as e:
            logger.error("checkpoint_corrupted", task_id=task_id, error=str(e))
            raise CheckpointCorruptedError(
                f"检查点 {task_id} 数据损坏: {e}"
            ) from e