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


def test_security_guard():
    from orbit.security.guard import WorkspaceGuard
    g = WorkspaceGuard("/tmp")
    assert g is not None


def test_ablation_context():
    from orbit.effectiveness.ablation import AblationContext
    assert not AblationContext.is_disabled("test")


def test_snapshot_manager_init(tmp_path):
    from orbit.backup.snapshot import SnapshotManager
    s = SnapshotManager(str(tmp_path))
    assert s is not None


def test_versioning_registry():
    from orbit.versioning.registry import VersionRegistry
    r = VersionRegistry()
    assert r is not None


def test_worktree_manager():
    from orbit.worktree.manager import WorktreeManager
    w = WorktreeManager()
    assert w is not None


def test_stream_sse():
    from orbit.stream.sse import router
    assert router is not None


def test_compose_engine():
    from orbit.compose.engine import ComposeEngine
    e = ComposeEngine()
    assert e is not None
