"""沙箱隔离场景——超时强杀/权限拒绝/网络隔离/OOM。

验证代码隔离执行的各种故障模式。
"""

from __future__ import annotations

import pytest

from tests.lib.mocks.sandbox import MockSandbox
from orbit.sandbox.executor import SandboxExecutionError, SandboxTimeoutError, SandboxError


@pytest.mark.scenario_sandbox
async def test_sandbox_timeout_kills_infinite_loop() -> None:
    """沙箱超时→SandboxTimeoutError。"""
    sandbox = MockSandbox(timeout_seconds=5)

    with pytest.raises(SandboxTimeoutError):
        await sandbox.run("while True: pass")


@pytest.mark.scenario_sandbox
async def test_sandbox_permission_denied() -> None:
    """代码尝试写入系统路径→权限拒绝。"""
    sandbox = MockSandbox(permission_denied=True)

    with pytest.raises(SandboxExecutionError, match="Permission denied"):
        await sandbox.run("open('/etc/passwd', 'w').write('hacked')")


@pytest.mark.scenario_sandbox
async def test_sandbox_oom_kills_container() -> None:
    """内存超限→OOM Killer 强杀。"""
    sandbox = MockSandbox(oom=True)

    with pytest.raises(SandboxError, match="OOM"):
        await sandbox.run("x = [0] * 10**12")


@pytest.mark.scenario_sandbox
async def test_sandbox_unsupported_language() -> None:
    """不支持的编程语言→SandboxError。"""
    sandbox = MockSandbox()

    with pytest.raises(SandboxError, match="仅支持 python"):
        await sandbox.run("console.log('hello')", language="javascript")


@pytest.mark.scenario_sandbox
async def test_sandbox_nonzero_exit_code() -> None:
    """代码非零退出→SandboxExecutionError。"""
    sandbox = MockSandbox(exit_code=1, stderr="NameError: name 'x' is not defined")

    with pytest.raises(SandboxExecutionError, match="exit=1"):
        await sandbox.run("print(x)")


@pytest.mark.scenario_sandbox
async def test_sandbox_normal_execution() -> None:
    """正常执行→返回 stdout。"""
    sandbox = MockSandbox(stdout="hello world")

    result = await sandbox.run("print('hello world')")
    assert result == "hello world"
    assert sandbox.call_count == 1
