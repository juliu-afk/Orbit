"""sandbox/process_sandbox.py unit tests — ProcessSandbox init, availability, error paths.
Coverage sprint B2-4: 53% → >=70%.
"""
from __future__ import annotations

import pytest

from orbit.sandbox.executor import SandboxError
from orbit.sandbox.process_sandbox import ProcessSandbox, _drop_privileges


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sandbox():
    return ProcessSandbox()


@pytest.fixture
def sandbox_fast():
    """Sandbox with short timeout for test speed."""
    return ProcessSandbox(timeout=5)


# ── __init__ ──────────────────────────────────────────────


class TestInit:
    def test_default_timeout(self, sandbox):
        """Default timeout from DEFAULT_TIMEOUT."""
        from orbit.sandbox.executor import DEFAULT_TIMEOUT
        assert sandbox.timeout == DEFAULT_TIMEOUT

    def test_custom_timeout(self):
        s = ProcessSandbox(timeout=10)
        assert s.timeout == 10


# ── is_available ──────────────────────────────────────────


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_always_available(self, sandbox):
        """ProcessSandbox is always available (subprocess is the ultimate fallback)."""
        assert await sandbox.is_available() is True


# ── run error paths ───────────────────────────────────────


class TestRunErrors:
    @pytest.mark.asyncio
    async def test_unsupported_language(self, sandbox):
        """Non-python language → SandboxError."""
        with pytest.raises(SandboxError, match="MVP"):
            await sandbox.run("echo hello", language="javascript")

    @pytest.mark.asyncio
    async def test_successful_run(self, sandbox):
        """Valid python code → returns stdout."""
        result = await sandbox.run("print('hello sandbox')", language="python")
        assert "hello sandbox" in result


# ── _drop_privileges ──────────────────────────────────────


class TestDropPrivileges:
    def test_function_exists(self):
        """_drop_privileges is callable (won't run on Windows but structure is valid)."""
        assert callable(_drop_privileges)
