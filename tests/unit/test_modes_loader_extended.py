"""modes/loader.py extended tests — ModeLoader init, caching.
Coverage sprint 4-3: 69% → >=80%.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from orbit.modes.loader import ModeLoader


class TestModeLoaderInit:
    def test_default_dir(self):
        loader = ModeLoader()
        assert loader._modes_dir is not None

    def test_custom_dir(self, tmp_path):
        loader = ModeLoader(modes_dir=tmp_path)
        assert loader._modes_dir == Path(tmp_path)

    def test_cache_starts_empty(self):
        loader = ModeLoader()
        assert loader._cache == {}

    def test_load_missing_returns_none(self):
        """Loading non-existent mode → returns None (fail-open)."""
        import tempfile
        d = tempfile.mkdtemp()
        loader = ModeLoader(modes_dir=d)
        result = loader.load("nonexistent_mode")
        assert result is None
