"""/dream 定时调度器 (5B.3)."""
from __future__ import annotations
import os, time
from datetime import UTC, datetime
from pathlib import Path
import structlog
from orbit.dream.models import DreamResult, DreamStatus

logger = structlog.get_logger("orbit.dream.scheduler")
DREAM_INTERVAL_SECONDS = 7 * 86400
LAST_DREAM_FILE = ".orbit/last_dream"

class DreamScheduler:
    def __init__(self, engine=None, interval_seconds=DREAM_INTERVAL_SECONDS, last_dream_file=LAST_DREAM_FILE):
        self._engine = engine; self._interval = interval_seconds; self._last_dream_file = last_dream_file
    def should_run(self):
        try:
            mtime = os.path.getmtime(self._last_dream_file)
            now = time.time()
            if mtime > now: return False
            return (now - mtime) >= self._interval
        except FileNotFoundError: return True
    async def check_and_run(self):
        if not self.should_run(): return DreamResult(status=DreamStatus.SKIPPED, notes=["间隔未到"])
        if self._engine is None: return DreamResult(status=DreamStatus.SKIPPED, notes=["引擎未注入"])
        logger.info("dream_auto_triggered")
        result = await self._engine.run()
        self._mark_done()
        return result
    def _mark_done(self):
        path = Path(self._last_dream_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(datetime.now(UTC).isoformat())
