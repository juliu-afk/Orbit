"""Mock 检查点管理器——替代 checkpoint/manager.py:CheckpointManager。

模拟双层存储（Redis热/PG冷）的故障模式：
- Redis 断连 → 降级内存
- PG 不可用 → 降级纯内存
- 版本冲突 → 乐观锁失败

使用示例:
    # 正常模式
    mock = MockCheckpointManager()
    # Redis 不可用
    mock = MockCheckpointManager(redis_available=False)
    # 版本冲突
    mock = MockCheckpointManager(version_conflict_on_save=True)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from orbit.checkpoint.manager import (
    CheckpointCorruptedError,
    CheckpointData,
    CheckpointError,
    CheckpointNotFoundError,
)

logger = structlog.get_logger()


class MockCheckpointManager:
    """Mock 检查点管理器——替代 checkpoint/manager.py:CheckpointManager。

    100% 兼容 CheckpointManager.save()/load() 接口签名。
    纯内存实现，不依赖 Redis/PG。
    """

    def __init__(
        self,
        redis_available: bool = True,
        pg_available: bool = True,
        version_conflict_on_save: bool = False,
    ) -> None:
        """初始化 Mock 检查点管理器。

        Args:
            redis_available: True→模拟 Redis 可用（影响内部路径选择，不影响功能）
            pg_available: True→模拟 PG 可用
            version_conflict_on_save: True→第二次 save 同 task_id 抛 CheckpointError
        """
        self.redis_available = redis_available
        self.pg_available = pg_available
        self.version_conflict_on_save = version_conflict_on_save

        # 内存存储（模拟 Redis + PG）
        self._store: dict[str, CheckpointData] = {}
        self._save_count: dict[str, int] = {}  # task_id → 保存次数（用于版本冲突检测）

        # 调用追踪
        self.saved: list[tuple[str, CheckpointData]] = []
        self.loaded: list[str] = []

    # ── 链式配置方法 ──────────────────────────────────────

    def without_redis(self) -> "MockCheckpointManager":
        """模拟 Redis 不可用。"""
        self.redis_available = False
        return self

    def without_pg(self) -> "MockCheckpointManager":
        """模拟 PG 不可用。"""
        self.pg_available = False
        return self

    def with_version_conflict(self) -> "MockCheckpointManager":
        """模拟乐观锁版本冲突（第二次 save 失败）。"""
        self.version_conflict_on_save = True
        return self

    # ── 生产接口兼容方法 ──────────────────────────────────

    async def save(self, task_id: str, data: CheckpointData) -> None:
        """保存检查点——兼容 CheckpointManager.save()。

        Raises:
            CheckpointError: version_conflict_on_save=True 且非首次 save 时
        """
        save_count = self._save_count.get(task_id, 0) + 1
        self._save_count[task_id] = save_count

        # 版本冲突模拟（第二次保存同 task_id 时触发）
        if self.version_conflict_on_save and save_count > 1:
            raise CheckpointError(
                f"Version conflict: task {task_id} already has version {save_count - 1}"
            )

        # 更新时间戳
        data.updated_at = time.time()
        self._store[task_id] = data
        self.saved.append((task_id, data))

        # 降级路径日志（测试断言可据此验证降级行为）
        if not self.redis_available and not self.pg_available:
            logger.info("checkpoint_degraded_memory", task_id=task_id)

    async def load(self, task_id: str) -> CheckpointData | None:
        """加载检查点——兼容 CheckpointManager.load()。

        Returns:
            CheckpointData 或 None（未找到检查点）

        Raises:
            CheckpointNotFoundError: 无检查点记录
        """
        self.loaded.append(task_id)
        data = self._store.get(task_id)
        if data is None:
            # 生产代码 load() 在找不到时 raise，不是 return None
            # 但为了灵活性，Mock 不 raise——由调用方决定
            return None
        return data

    async def delete(self, task_id: str) -> None:
        """删除检查点。"""
        self._store.pop(task_id, None)
        self._save_count.pop(task_id, None)

    # ── 辅助方法 ──────────────────────────────────────────

    @property
    def checkpoint_count(self) -> int:
        """已保存的检查点数量。"""
        return len(self._store)

    def reset(self) -> None:
        """重置所有状态。"""
        self._store.clear()
        self._save_count.clear()
        self.saved.clear()
        self.loaded.clear()
