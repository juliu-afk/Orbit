"""覆盖率补测——gateway/circuit_breaker.py + backup/snapshot.py."""

from __future__ import annotations

import pytest

from orbit.backup.snapshot import Snapshotter
from orbit.gateway.circuit_breaker import CircuitBreaker
from orbit.gateway.schemas import CircuitBreakerState


class TestCircuitBreakerState:
    def test_defaults(self):
        state = CircuitBreakerState()
        assert state.failure_count == 0
        assert state.opened_at is None

    def test_half_open_default_false(self):
        state = CircuitBreakerState()
        assert state.half_open is False


class TestCircuitBreaker:
    def test_init_defaults(self):
        cb = CircuitBreaker()
        assert cb.failure_threshold > 0

    def test_init_custom(self):
        cb = CircuitBreaker(failure_threshold=5, cooldown=30)
        assert cb.failure_threshold == 5

    @pytest.mark.asyncio
    async def test_before_call_closed(self):
        cb = CircuitBreaker()
        await cb.before_call("test-model")


class TestSnapshotter:
    def test_list_snapshots_empty(self, tmp_path):
        s = Snapshotter(backup_dir=str(tmp_path))
        assert s.list_snapshots() == []

    def test_backup_dir(self, tmp_path):
        s = Snapshotter(backup_dir=str(tmp_path))
        assert s.backup_dir == str(tmp_path)
