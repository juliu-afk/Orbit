"""检查点工厂——CheckpointData。

用于创建确定性的检查点数据，模拟调度器状态保存。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from orbit.checkpoint.manager import CheckpointData


def create_checkpoint(
    task_id: str | None = None,
    state: str = "CODING",
    retry_count: int = 0,
    progress: float = 0.5,
    context: dict[str, Any] | None = None,
    version: int = 1,
    **kwargs: Any,
) -> CheckpointData:
    """创建 CheckpointData——检查点数据。

    Args:
        task_id: 任务 ID（None→自动生成 UUID）
        state: 调度器状态机当前状态（IDLE/PARSING/PLANNING/CODING/VERIFYING/DONE/FAILED）
        retry_count: 重试次数
        progress: 进度（0.0-1.0）
        context: 上下文数据
        version: 乐观锁版本号
    """
    if task_id is None:
        task_id = str(uuid.uuid4())
    if context is None:
        context = {"prd": "测试需求", "agent_role": "developer"}

    return CheckpointData(
        task_id=task_id,
        state=state,
        retry_count=retry_count,
        progress=progress,
        context=context,
        updated_at=time.time(),
        version=version,
    )
