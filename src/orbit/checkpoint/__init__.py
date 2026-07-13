"""检查点模块——双层存储 + 偏离日志。

导出:
    CheckpointData, CheckpointManager — 检查点持久化
    DeviationEntry, DeviationLogger, DeviationSeverity, is_deviation — 偏离日志 (V15.2+)
"""

from orbit.checkpoint.manager import (
    CheckpointCorruptedError, CheckpointData, CheckpointError,
    CheckpointManager, CheckpointNotFoundError,
)
from orbit.checkpoint.deviation import (
    DeviationEntry, DeviationLogger, DeviationSeverity, is_deviation,
)

__all__ = [
    "CheckpointData", "CheckpointManager",
    "CheckpointError", "CheckpointNotFoundError", "CheckpointCorruptedError",
    "DeviationEntry", "DeviationLogger", "DeviationSeverity", "is_deviation",
]
