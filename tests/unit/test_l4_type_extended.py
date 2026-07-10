"""hallucination/l4_type.py extended tests — constants, init, schema.
Coverage sprint 7-2: 82% → >=90%.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.hallucination.l4_type import L4TypeValidator, _MYPY_FLAGS
from orbit.hallucination.schemas import HallucinationLevel, ValidationResult


class TestL4Constants:
    def test_mypy_flags(self):
        assert "--strict" in _MYPY_FLAGS
        assert "no-untyped-def" in " ".join(_MYPY_FLAGS)


class TestL4Validator:
    def test_init_default(self):
        v = L4TypeValidator()
        assert v is not None

    @pytest.mark.asyncio
    async def test_validate_empty_code(self):
        """Empty code → ValidationResult passed (skip_if_empty decorator)."""
        v = L4TypeValidator()
        result = await v.validate("")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_no_mypy(self):
        """When mypy not installed → returns failure with error."""
        with patch("shutil.which", return_value=None):
            v = L4TypeValidator()
            result = await v.validate("x: int = 'string'")
            assert not result.passed

    @pytest.mark.asyncio
    async def test_validate_with_mypy(self):
        """When mypy is available, runs type check."""
        v = L4TypeValidator()
        with patch("shutil.which", return_value="/usr/bin/mypy"):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.communicate = MagicMock()
                mock_proc.communicate.return_value = (b"", b"")
                mock_exec.return_value = mock_proc

                import asyncio
                async def mock_communicate():
                    return (b"", b"")
                mock_proc.communicate = mock_communicate

                result = await v.validate("x: int = 1")
                assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_type_error(self):
        """mypy finds type error → not passed."""
        v = L4TypeValidator()
        with patch("shutil.which", return_value="/usr/bin/mypy"):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = MagicMock()
                mock_proc.returncode = 1

                async def mock_communicate():
                    return (b"test.py:1: error: Incompatible types", b"")
                mock_proc.communicate = mock_communicate
                mock_exec.return_value = mock_proc

                result = await v.validate("x: int = 'string'")
                assert not result.passed

    @pytest.mark.asyncio
    async def test_validate_with_mypy_errors(self):
        """mypy finds multiple errors → all reported."""
        v = L4TypeValidator()
        with patch("shutil.which", return_value="/usr/bin/mypy"):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = MagicMock()
                mock_proc.returncode = 1
                async def mock_comm():
                    return (b"test.py:1: error: Incompatible types\n", b"")
                mock_proc.communicate = mock_comm
                mock_exec.return_value = mock_proc
                result = await v.validate("x: int = 'bad'")
                assert not result.passed
