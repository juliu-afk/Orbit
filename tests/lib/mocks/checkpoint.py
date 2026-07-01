"""Mock 检查点管理器——替代 checkpoint/manager.py:CheckpointManager。

模拟双层存储（Redis热/PG冷）的故障模式：Redis断连/PG不可用/版本冲突。
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from orbit.checkpoint.manager import CheckpointData, CheckpointError

logger = structlog.get_logger()


class MockCheckpointManager:
    """Mock 检查点管理器——替代 checkpoint/manager.py:CheckpointManager。100% 兼容 save/load 接口。"""

    def __init__(
        self,
        redis_available: bool = True,
        pg_available: bool = True,
        version_conflict_on_save: bool = False,
    ) -> None:
        self.redis_available = redis_available
        self.pg_available = pg_available
        self.version_conflict_on_save = version_conflict_on_save
        self._store: dict[str, CheckpointData] = {}
        self._save_count: dict[str, int] = {}
        self.saved: list[tuple[str, CheckpointData]] = []
        self.loaded: list[str] = []

    def without_redis(self) -> "MockCheckpointManager":
        self.redis_available = False
        return self

    def without_pg(self) -> "MockCheckpointManager":
        self.pg_available = False
        return self

    def with_version_conflict(self) -> "MockCheckpointManager":
        self.version_conflict_on_save = True
        return self

    async def save(self, task_id: str, data: CheckpointData) -> None:
        save_count = self._save_count.get(task_id, 0) + 1
        self._save_count[task_id] = save_count

        if self.version_conflict_on_save and save_count > 1:
            raise CheckpointError(f"Version conflict: task {task_id} already has version {save_count - 1}")

        data.updated_at = time.time()
        self._store[task_id] = data
        self.saved.append((task_id, data))

        if not self.redis_available and not self.pg_available:
            logger.info("checkpoint_degraded_memory", task_id=task_id)

    async def load(self, task_id: str) -> CheckpointData | None:
        self.loaded.append(task_id)
        return self._store.get(task_id)

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)
        self._save_count.pop(task_id, None)

    def save_sync(self, task_id: str, state: str, data: CheckpointData) -> None:
        """同步保存检查点——供 Builder 测试断言使用。

        WHY 独立于 async save(): Builder 的 _save_checkpoint 是 sync 方法，
        无法 await。此方法直接操作 _store，供测试断言 checkpoint_count。
        """
        key = f"{task_id}:{state}"
        self._store[key] = data
        self.saved.append((key, data))

    @property
    def checkpoint_count(self) -> int:
        return len(self._store)

    def reset(self) -> None:
        self._store.clear()
        self._save_count.clear()
        self.saved.clear()
        self.loaded.clear()
