"""graph/watcher.py unit tests — GraphFileHandler + GraphWatcher lifecycle.
Coverage sprint B1-5: 0% → >=80%.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── Fake watchdog base class ──────────────────────────────
# WHY real class not MagicMock: GraphFileHandler.__init__ calls super().__init__(),
# which fails on MagicMock (StopIteration). Use a dummy class.


class FakeFileSystemEventHandler:
    """Dummy base class that accepts any __init__ args."""
    def __init__(self, *args, **kwargs):
        pass


# Import after patching
with patch("watchdog.events.FileSystemEventHandler", FakeFileSystemEventHandler):
    with patch("watchdog.observers.Observer") as MockObserver:
        from orbit.graph.watcher import GraphFileHandler, GraphWatcher  # noqa: E402


# ── GraphFileHandler ──────────────────────────────────────


class TestGraphFileHandler:
    """Test GraphFileHandler — file change event handling."""

    def test_init(self):
        """Handler stores code_graph reference."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        assert handler._cg is cg

    def test_on_modified_directory_skipped(self):
        """Directory events are ignored."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        event = MagicMock()
        event.is_directory = True

        handler.on_modified(event)
        cg.incremental_update.assert_not_called()

    def test_on_modified_unwatched_ext(self):
        """Files with unwatched extensions (.md) are skipped."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/file.md"

        handler.on_modified(event)
        cg.incremental_update.assert_not_called()

    def test_on_modified_watched_ext(self):
        """.py / .ts files trigger incremental_update via asyncio.run."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/project/module.py"

        with patch("asyncio.run") as mock_run:
            handler.on_modified(event)
            mock_run.assert_called_once()

    def test_on_modified_no_src_path(self):
        """Event with empty src_path is skipped."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        event = MagicMock()
        event.is_directory = False
        event.src_path = ""

        handler.on_modified(event)
        cg.incremental_update.assert_not_called()

    def test_on_modified_update_error(self):
        """Update failure is caught — does not propagate."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/project/file.py"

        with patch("asyncio.run", side_effect=RuntimeError("update failed")):
            # Should not raise — exception is caught and logged
            handler.on_modified(event)

    def test_on_created_delegates_to_on_modified(self):
        """on_created calls on_modified (same logic)."""
        cg = MagicMock()
        handler = GraphFileHandler(cg)
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/project/new_file.py"

        with patch("asyncio.run") as mock_run:
            handler.on_created(event)
            mock_run.assert_called_once()


# ── GraphWatcher ──────────────────────────────────────────


class TestGraphWatcher:
    """Test GraphWatcher — start/stop lifecycle."""

    def test_init(self):
        """Watcher stores config; observer starts as None."""
        cg = MagicMock()
        w = GraphWatcher(cg, "/test/project")
        assert w._cg is cg
        assert w._watch_dir == "/test/project"
        assert w._observer is None

    def test_start_creates_observer(self):
        """start() creates Observer, schedules handler, starts thread."""
        cg = MagicMock()
        w = GraphWatcher(cg, "/test/project")
        w.start()
        assert w._observer is not None
        w._observer.schedule.assert_called_once()
        w._observer.start.assert_called_once()

    def test_stop_no_observer_is_noop(self):
        """stop() when observer is None — no crash."""
        cg = MagicMock()
        w = GraphWatcher(cg, "/test/project")
        w.stop()  # should not raise

    def test_stop_with_observer(self):
        """stop() calls observer.stop() + join(timeout=5) + sets None."""
        cg = MagicMock()
        w = GraphWatcher(cg, "/test/project")
        w.start()
        observer = w._observer
        w.stop()
        observer.stop.assert_called_once()
        observer.join.assert_called_once_with(timeout=5)
        assert w._observer is None

    def test_start_twice_replaces_observer(self):
        """Second start() schedules and starts again (new handler)."""
        cg = MagicMock()
        w = GraphWatcher(cg, "/test/project")
        w.start()
        w.start()  # should not raise — replaces handler
        w._observer.schedule.assert_called()
        w._observer.start.assert_called()
