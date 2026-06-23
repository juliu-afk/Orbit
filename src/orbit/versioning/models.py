"""版本注册表数据模型 (Step 7.4/7.5 PR #2).

VersionRecord: 版本记录 (semver + timestamp)
MigrationRecord: Schema 迁移记录
ReleaseEvent: 发布/回滚审计事件
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VersionRecord:
    """版本记录——存储已安装的版本号及安装时间。"""

    version: str  # semver: v1.2.3
    installed_at: float  # time.time()
    description: str = ""  # 版本说明 (changelog 摘要)
    is_active: bool = True  # 是否为当前活跃版本

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "installed_at": self.installed_at,
            "description": self.description,
            "is_active": self.is_active,
        }


@dataclass
class MigrationRecord:
    """Schema 迁移记录——追踪数据库变更历史。"""

    migration_id: str  # 迁移脚本标识: V001__init, V002__add_column
    version: str  # 对应版本号
    applied_at: float
    checksum: str = ""  # 迁移脚本 SHA256, 用于验证脚本未被篡改
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "version": self.version,
            "applied_at": self.applied_at,
            "checksum": self.checksum,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class ReleaseEvent:
    """发布/回滚审计事件。"""

    event_type: str  # deploy | rollback | canary_start | canary_end | canary_abort
    version: str
    previous_version: str = ""
    traffic_ratio: float = 0.0  # 金丝雀流量比例 (0.0=全量/-1.0=回滚)
    trigger: str = ""  # manual | auto_slo | auto_token
    timestamp: float = 0.0
    success: bool = True
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "version": self.version,
            "previous_version": self.previous_version,
            "traffic_ratio": self.traffic_ratio,
            "trigger": self.trigger,
            "timestamp": self.timestamp,
            "success": self.success,
            "details": self.details,
        }
