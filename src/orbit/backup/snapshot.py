"""快照创建 (Step 7.4/7.5 PR #1).

支持 SQLite .backup 导出 + 纯文件复制。
自动创建快照目录，生成 SnapshotMeta。
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from datetime import UTC, datetime

import structlog

from orbit.backup.integrity import compute_hash
from orbit.backup.models import SnapshotMeta

logger = structlog.get_logger("orbit.backup")

DEFAULT_BACKUP_DIR = "data/backups"


class Snapshotter:
    """快照创建器——SQLite dump + 文件复制。

    用法:
        s = Snapshotter()
        meta = s.snapshot_sqlite("data/knowledge.db", db_type="knowledge")
        meta = s.snapshot_file("data/checkpoint.json", db_type="checkpoint")
    """

    def __init__(self, backup_dir: str = DEFAULT_BACKUP_DIR) -> None:
        self._dir = backup_dir
        os.makedirs(self._dir, exist_ok=True)

    def snapshot_sqlite(self, source_path: str, db_type: str = "sqlite") -> SnapshotMeta:
        """创建 SQLite 数据库快照。

        WHY sqlite3 .backup API 而非文件复制:
        .backup 使用在线备份 API，在 WAL 模式下也能拿到一致性快照，
        不会出现文件复制时读到半写页面的问题。
        """
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_id = f"{db_type}_{ts}"
        dest = os.path.join(self._dir, f"{snap_id}.db")

        # 源数据库读取
        src = sqlite3.connect(source_path)
        src.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # 强制 checkpoint，减少 WAL
        dst = sqlite3.connect(dest)
        src.backup(dst)
        dst.close()
        src.close()

        return self._build_meta(snap_id, dest, db_type)

    def snapshot_file(self, source_path: str, db_type: str = "file") -> SnapshotMeta:
        """创建普通文件快照（检查点/配置等）。"""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap_id = f"{db_type}_{ts}"
        ext = os.path.splitext(source_path)[1]
        dest = os.path.join(self._dir, f"{snap_id}{ext}")

        shutil.copy2(source_path, dest)

        return self._build_meta(snap_id, dest, db_type)

    def _build_meta(self, snap_id: str, path: str, db_type: str) -> SnapshotMeta:
        size = os.path.getsize(path)
        h = compute_hash(path)
        logger.info("snapshot_created", id=snap_id, size=size, db_type=db_type)
        return SnapshotMeta(
            snapshot_id=snap_id,
            path=path,
            size_bytes=size,
            integrity_hash=h,
            created_at=time.time(),
            db_type=db_type,
        )

    def list_snapshots(self, db_type: str = "") -> list[SnapshotMeta]:
        """docstring"""
        import glob

        pattern = (
            os.path.join(self._dir, "*.db")
            if not db_type
            else os.path.join(self._dir, f"{db_type}_*.db")
        )
        results: list[SnapshotMeta] = []
        for path in sorted(glob.glob(pattern), reverse=True):
            snap_id = os.path.splitext(os.path.basename(path))[0]
            try:
                size = os.path.getsize(path)
                integrity_hash = compute_hash(path)
                created = os.path.getmtime(path)
                parts = snap_id.split("_", 1)
                dtype = parts[0] if len(parts) > 1 else ""
                results.append(
                    SnapshotMeta(
                        snapshot_id=snap_id,
                        path=path,
                        size_bytes=size,
                        integrity_hash=integrity_hash,
                        created_at=created,
                        db_type=dtype,
                    )
                )
            except OSError:
                continue
        return results

    @property
    def backup_dir(self) -> str:
        return self._dir
