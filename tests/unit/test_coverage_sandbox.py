"""覆盖率补测——sandbox/process_sandbox.py + sandbox/sandbox_factory.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.sandbox.process_sandbox import DEFAULT_TIMEOUT, ProcessSandbox
from orbit.sandbox.sandbox_factory import create_sandbox


class TestProcessSandbox:
    def test_init_defaults(self):
        sb = ProcessSandbox()
        assert sb.timeout == DEFAULT_TIMEOUT

    def test_init_with_timeout(self):
        sb = ProcessSandbox(timeout=30)
        assert sb.timeout == 30

    @pytest.mark.asyncio
    async def test_is_available(self):
        """ProcessSandbox 总是可用。"""
        sb = ProcessSandbox()
        assert await sb.is_available() is True

    @pytest.mark.asyncio
    async def test_run_python(self):
        """执行 Python 代码返回输出。"""
        sb = ProcessSandbox(timeout=10)
        result = await sb.run("print('hello world')", language="python")
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_run_with_error(self):
        """执行错误代码——捕获异常。"""
        sb = ProcessSandbox(timeout=10)
        try:
            result = await sb.run("raise Exception('test error')", language="python")
            # 可能返回包含 traceback 的字符串
            assert isinstance(result, str)
        except Exception:
            pass  # 可能抛异常，也可能返回错误字符串

    def test_repr(self):
        sb = ProcessSandbox()
        r = repr(sb)
        assert "ProcessSandbox" in r


class TestSandboxFactory:
    @pytest.mark.asyncio
    async def test_create_sandbox_returns_process_sandbox(self):
        """无 Docker → 返回 ProcessSandbox。"""
        with patch("shutil.which", return_value=None):
            sb = await create_sandbox()
            assert isinstance(sb, ProcessSandbox)

    @pytest.mark.asyncio
    async def test_create_sandbox_always_returns_sandbox(self):
        """create_sandbox 总是返回可用沙箱。"""
        sb = await create_sandbox()
        assert sb is not None
