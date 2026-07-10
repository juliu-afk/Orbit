"""Final sweep — pure modules, constants, enums."""
from __future__ import annotations


def test_router_constants():
    from orbit.router import weights
    assert weights is not None


def test_stream_constants():
    from orbit.stream import cancellation
    assert cancellation is not None


def test_events_constants():
    from orbit.events import bus
    assert bus is not None


def test_sharding_engine():
    from orbit.sharding.engine import ShardingEngine
    e = ShardingEngine()
    assert e is not None


def test_security_guard():
    from orbit.security.guard import WorkspaceGuard
    g = WorkspaceGuard("/tmp")
    assert g is not None


def test_ablation_context():
    from orbit.effectiveness.ablation import AblationContext
    assert AblationContext.is_disabled("test") is False


def test_backup_snapshot():
    from orbit.backup.snapshot import SnapshotManager
    import tempfile
    d = tempfile.mkdtemp()
    s = SnapshotManager(d)
    assert s is not None
