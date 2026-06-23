"""从快照恢复 (Step 7.4/7.5 PR #1).

恢复流程: 1) 验证快照完整性 → 2) 备份当前文件 → 3) 覆盖恢复 → 4) 验证恢复后文件
"""

from __future__ import annotations

import os
import shutil
import time

import structlog

from orbit.backup.integrity import verify_integrity
from orbit.backup.models import RestoreResult, SnapshotMeta

logger = structlog.get_logger("orbit.backup")


class Restorer:
    """快照恢复器。

    用法:
        r = Restorer()
        result = r.restore(meta, target_path="data/knowledge.db")
        if result.success:
            print("恢复成功")
    """

    def restore(self, meta: SnapshotMeta, target_path: str) -> RestoreResult:
        """从快照恢复到目标路径。

        步骤:
        1. 验证快照文件完整性 (SHA256)
        2. 备份当前目标文件 (如果存在) 为 <target>.backup
        3. 复制快照到目标
        4. 验证恢复后文件完整性
        """
        start = time.time()

        # 1. 完整性验证
        if not verify_integrity(meta.path, meta.integrity_hash):
            logger.warning("restore_integrity_fail", snapshot_id=meta.snapshot_id)
            return RestoreResult(
                success=False,
                snapshot_id=meta.snapshot_id,
                target_path=target_path,
                reason="快照完整性校验失败:SHA256 不匹配",
            )

        # 2. 备份当前文件
        if os.path.exists(target_path):
            backup_target = target_path + ".backup"
            shutil.copy2(target_path, backup_target)
            logger.info("pre_restore_backup", target=target_path, backup=backup_target)

        # 3. 复制快照到目标
        try:
            shutil.copy2(meta.path, target_path)
        except OSError as e:
            return RestoreResult(
                success=False,
                snapshot_id=meta.snapshot_id,
                target_path=target_path,
                reason=f"文件复制失败:{e}",
            )

        # 4. 验证恢复后文件
        integrity_ok = verify_integrity(target_path, meta.integrity_hash)

        elapsed = (time.time() - start) * 1000
        result = RestoreResult(
            success=integrity_ok,
            snapshot_id=meta.snapshot_id,
            target_path=target_path,
            integrity_ok=integrity_ok,
            elapsed_ms=elapsed,
        )

        if result.success:
            logger.info("restore_ok", snapshot_id=meta.snapshot_id, elapsed_ms=round(elapsed))
        else:
            logger.warning("restore_verify_fail", snapshot_id=meta.snapshot_id)

        return result
