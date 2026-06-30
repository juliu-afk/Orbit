"""Actor 生命周期管理 (5C.4)."""

from __future__ import annotations
import time
import structlog

logger = structlog.get_logger("orbit.actors")
ACTOR_STALE_SECONDS = 300
ACTOR_REAP_TOLERANCE = 10


class ActorLifecycle:
    """子Agent 生命周期跟踪——心跳 + stale检测."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._last_heartbeat = time.time()
        self._started_at = time.time()
        self._reaped = False

    def heartbeat(self) -> None:
        self._last_heartbeat = time.time()

    @property
    def is_stale(self) -> bool:
        return (time.time() - self._last_heartbeat) > (ACTOR_STALE_SECONDS + ACTOR_REAP_TOLERANCE)

    def reap(self) -> None:
        if self._reaped:
            return
        self._reaped = True
        logger.info("actor_reaped", agent_id=self.agent_id, age=time.time() - self._started_at)
