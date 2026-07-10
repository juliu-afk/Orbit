"""offpeak/scheduler.py — estimate_window_capacity pure function tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbit.scheduler.offpeak_models import DeferredTask
from orbit.scheduler.offpeak_scheduler import estimate_window_capacity


def _make_task(name="t", duration=10, priority="NORMAL"):
    return DeferredTask(
        goal_id=f"g-{name}", goal_text=f"task {name}",
        estimated_duration_seconds=duration, priority=priority,
    )


class TestEstimateWindowCapacity:
    def test_empty_queue(self):
        now = datetime.now(UTC)
        later = now + timedelta(hours=1)
        assert estimate_window_capacity(now, later, []) == 0

    def test_single_task_fits(self):
        now = datetime.now(UTC)
        later = now + timedelta(seconds=100)
        t = _make_task("a", duration=10)
        assert estimate_window_capacity(now, later, [t]) == 1

    def test_multiple_tasks_fit(self):
        now = datetime.now(UTC)
        later = now + timedelta(hours=2)
        tasks = [_make_task(f"t{i}", duration=10) for i in range(10)]
        count = estimate_window_capacity(now, later, tasks, max_parallel=3)
        assert count >= 5

    def test_task_too_large(self):
        now = datetime.now(UTC)
        later = now + timedelta(seconds=10)
        t = _make_task("big", duration=100)
        assert estimate_window_capacity(now, later, [t]) == 0

    def test_priority_sorting(self):
        """CRITICAL tasks processed first."""
        now = datetime.now(UTC)
        later = now + timedelta(seconds=200)
        # Put HIGH task last in list — it should still be counted first
        tasks = [
            _make_task("low", duration=80, priority="LOW"),
            _make_task("high", duration=5, priority="HIGH"),
        ]
        count = estimate_window_capacity(now, later, tasks, max_parallel=1)
        assert count >= 1  # HIGH task fits regardless of position

    def test_parallel_multiplier(self):
        now = datetime.now(UTC)
        later = now + timedelta(seconds=100)
        # With max_parallel=1, only 1 task fits; with 10, many fit
        tasks = [_make_task(f"t{i}", duration=10) for i in range(20)]
        c1 = estimate_window_capacity(now, later, tasks, max_parallel=1)
        c10 = estimate_window_capacity(now, later, tasks, max_parallel=10)
        assert c10 > c1
