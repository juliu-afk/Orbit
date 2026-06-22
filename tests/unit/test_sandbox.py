"""MVP-03 Docker 沙箱测试。

Docker 不可用时（CI/无 Docker 环境）测试 is_available 返回 False，
不依赖真实 Docker。真实执行需集成测试环境。
"""
from __future__ import annotations

import pytest

from orbit.sandbox.executor import (
    Sandbox,
    SandboxError,
    SandboxExecutionError,
    SandboxTimeoutError,
)


@pytest.fixture
def sandbox():
    return Sandbox(image="python:3.12-slim", timeout=10)


def test_sandbox_init_defaults(sandbox):
    """默认配置校验。"""
    assert sandbox.image == "python:3.12-slim"
    assert sandbox.timeout == 10
    assert sandbox._docker_available is None  # 未检测


@pytest.mark.asyncio
async def test_unsupported_language_raises(sandbox):
    """非 python 语言抛 SandboxError。"""
    with pytest.raises(SandboxError, match="不支持"):
        await sandbox.run("console.log('x')", language="javascript")


@pytest.mark.asyncio
async def test_docker_unavailable_raises(sandbox, monkeypatch):
    """Docker 不可用时 run 抛 SandboxError。"""

    async def fake_available():
        return False

    monkeypatch.setattr(sandbox, "is_available", fake_available)
    with pytest.raises(SandboxError, match="Docker 不可用"):
        await sandbox.run("print('hello')")


@pytest.mark.asyncio
async def test_is_available_false_when_no_docker(monkeypatch):
    """docker 不在 PATH 时 is_available 返回 False。"""
    sb = Sandbox()
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    result = await sb.is_available()
    assert result is False


@pytest.mark.asyncio
async def test_timeout_error(monkeypatch):
    """超时抛 SandboxTimeoutError。"""
    sb = Sandbox(timeout=1)

    # mock is_available 返回 True
    async def fake_available():
        return True

    monkeypatch.setattr(sb, "is_available", fake_available)

    # mock create_subprocess_exec 触发超时
    import asyncio

    class FakeProc:
        returncode = 0

        async def communicate(self):
            await asyncio.sleep(10)  # 远超 timeout=1
            return (b"", b"")

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(SandboxTimeoutError, match="超时"):
        await sb.run("import time; time.sleep(10)")


@pytest.mark.asyncio
async def test_nonzero_exit_raises_execution_error(monkeypatch):
    """非零退出码抛 SandboxExecutionError。"""
    sb = Sandbox(timeout=5)

    async def fake_available():
        return True

    monkeypatch.setattr(sb, "is_available", fake_available)

    import asyncio

    class FakeProc:
        returncode = 1

        async def communicate(self):
            return (b"", b"Traceback: ImportError")

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(SandboxExecutionError, match="exit=1"):
        await sb.run("raise ValueError('x')")


@pytest.mark.asyncio
async def test_successful_execution(monkeypatch):
    """成功执行返回 stdout。"""
    sb = Sandbox(timeout=5)

    async def fake_available():
        return True

    monkeypatch.setattr(sb, "is_available", fake_available)

    import asyncio

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (b"hello world\n", b"")

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    output = await sb.run("print('hello world')")
    assert "hello world" in output


@pytest.mark.asyncio
async def test_availability_cached(monkeypatch):
    """is_available 结果缓存（不重复检测）。"""
    sb = Sandbox()
    # 第一次返回 False（docker 不在）
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert await sb.is_available() is False
    # 第二次直接返回缓存
    assert sb._docker_available is False