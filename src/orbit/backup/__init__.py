"""Step 7.4/7.5 PR #1——备份管理器。

SQLite 快照 + SHA256 校验 + 恢复。
"""

from orbit.backup.integrity import compute_hash, verify_integrity
from orbit.backup.models import RestoreResult, SnapshotMeta
from orbit.backup.restore import Restorer
from orbit.backup.snapshot import Snapshotter

__all__ = [
    "Restorer",
    "RestoreResult",
    "SnapshotMeta",
    "Snapshotter",
    "compute_hash",
    "verify_integrity",
]
