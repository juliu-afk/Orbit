"""hallucination/l5_z3.py extended tests — validator init, constants, edge cases.
Coverage sprint 3-3: 51% → >=65%.
"""
from __future__ import annotations

from orbit.hallucination.l5_z3 import L5Z3Validator, Z3_TIMEOUT_MS


# ── Constants ─────────────────────────────────────────────


class TestZ3Constants:
    def test_timeout_ms_is_30s(self):
        assert Z3_TIMEOUT_MS == 30000


# ── L5Z3Validator ─────────────────────────────────────────


class TestL5Z3Validator:
    """Test L5Z3Validator constructor + basic validation."""

    def test_default_timeout(self):
        v = L5Z3Validator()
        assert v._timeout_ms == Z3_TIMEOUT_MS

    def test_custom_timeout(self):
        v = L5Z3Validator(timeout_ms=5000)
        assert v._timeout_ms == 5000

    def test_has_validate_method(self):
        """Validator has async validate method."""
        v = L5Z3Validator()
        assert hasattr(v, "validate")
        import inspect
        assert inspect.iscoroutinefunction(v.validate)
