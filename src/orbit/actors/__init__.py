"""Actor 子系统——子Agent 生命周期管理。

对标 MiMo Code actor/ 模块: registry (SQLite 状态机) + spawn (分配+注册+分叉) + watchdog (zombie 清理).
"""

from orbit.actors.models import ActorOutcome, ActorRecord, ActorStatus
from orbit.actors.registry import ActorRegistry
from orbit.actors.spawn import ActorSpawn, DeferredActor
from orbit.actors.watchdog import ActorWatchdog

__all__ = [
    "ActorOutcome",
    "ActorRecord",
    "ActorRegistry",
    "ActorSpawn",
    "ActorStatus",
    "ActorWatchdog",
    "DeferredActor",
]
