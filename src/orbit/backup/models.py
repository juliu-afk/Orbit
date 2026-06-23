"""备份管理器数据模型 (Step 7.4/7.5 PR #1).

SnapshotMeta: 快照元数据 (hash/size/timestamp)
RestoreResult: 恢复操作结果
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SnapshotMeta:
    """快照元数据。"""

    snapshot_id: str  # 快照唯一标识 (ISO8601 时间戳)
    path: str  # 快照文件路径
    size_bytes: int  # 文件大小
    integrity_hash: str  # SHA256 hex digest
    created_at: float  # time.time()
    db_type: str = ""  # sqlite | checkpoint | knowledge
    verified: bool = False  # 是否已通过完整性校验

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "integrity_hash": self.integrity_hash,
            "created_at": self.created_at,
            "db_type": self.db_type,
            "verified": self.verified,
        }


@dataclass
class RestoreResult:
    """恢复操作结果。"""

    success: bool
    snapshot_id: str = ""
    target_path: str = ""
    reason: str = ""  # 失败原因 (成功时为空)
    integrity_ok: bool = False  # 恢复后 SHA256 验证结果
    elapsed_ms: float = 0.0
