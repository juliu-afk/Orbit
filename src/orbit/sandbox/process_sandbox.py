"""进程级沙箱——Docker 不可用时的兜底隔离。

WHY 双层沙箱：Orbit 设计前提是代码执行必须有隔离。
Docker 不可用时，降级到进程级隔离而非裸奔。

Windows：subprocess + 独立工作目录 + 环境隔离
        （完整 AppContainer+Job+LowIL 方案待 Step 6.3，需 pywin32）
Unix：subprocess + rlimit(内存/进程数) + unshare(CLONE_NEWNET)

与 DockerSandbox 相同的 run(code, language) → str 接口，
调度器不感知底层机制差异。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import tempfile
from pathlib import Path

import structlog

from orbit.sandbox.executor import (
    DEFAULT_TIMEOUT,
    SandboxError,
    SandboxExecutionError,
    SandboxTimeoutError,
)

# P1-2: Windows AppContainer 隔离——条件导入 pywin32
try:
    import pywin32  # noqa: F401
    _HAS_APPCONTAINER = True
except ImportError:
    _HAS_APPCONTAINER = False

logger = structlog.get_logger("orbit.sandbox.process")


class ProcessSandbox:
    """进程级代码执行沙箱。

    实现与 Sandbox（DockerSandbox）相同的 run 接口。
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    async def run(self, code: str, language: str = "python") -> str:
        """执行代码片段，返回 stdout。

        Raises:
            SandboxError: 不可用 / 语言不支持
            SandboxTimeoutError: 超时
            SandboxExecutionError: 非零退出码
        """
        if language != "python":
            raise SandboxError(f"MVP 仅支持 python，不支持 {language}")

        if not await self.is_available():
            raise SandboxError("进程沙箱不可用")

        if sys.platform == "win32":
            return await self._run_windows(code)
        return await self._run_unix(code)

    async def is_available(self) -> bool:
        """进程沙箱总是可用——subprocess 是最低的兜底。

        Python 解释器存在 = 沙箱可用。
        """
        return True

    async def _run_windows(self, code: str) -> str:
        """Windows 进程隔离执行。

        P1-2: 有 pywin32 时走 AppContainer，无则降级 subprocess。
        """
        if _HAS_APPCONTAINER:
            return await self._run_windows_appcontainer(code)
        return await self._run_windows_subprocess(code)

    async def _run_windows_appcontainer(self, code: str) -> str:
        """AppContainer 沙箱执行——需 pywin32。

        TODO(security/P1-2): 实现完整 Windows AppContainer 隔离
        - 创建 AppContainer profile (CreateAppContainerProfile)
        - CreateProcess 时绑定 AppContainer SID
        - 禁止网络访问 (SID: INTERNET_CLIENT / WINAPI_CAPABILITY_INTERNET_CLIENT_SERVER)
        - 参考: https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation
        """
        logger.warning(
            "appcontainer_not_implemented_fallback_subprocess",
            code_len=len(code),
        )
        return await self._run_windows_subprocess(code)

    async def _run_windows_subprocess(self, code: str) -> str:
        """subprocess 隔离——CREATE_NO_WINDOW + 临时目录 + 环境白名单。

        当前兜底方案，待 pywin32 就绪后升级为 AppContainer。
        """
        with tempfile.TemporaryDirectory(prefix="orbit-sandbox-") as td:
            script = Path(td) / "code.py"
            script.write_text(code, encoding="utf-8")

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script),
                    cwd=td,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
                        "TEMP": td,
                        "TMP": td,
                    },
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=0x08000000 if hasattr(sys, "getwindowsversion") else 0,
                    # CREATE_NO_WINDOW = 0x08000000，避免弹控制台窗口
                )
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except TimeoutError as e:
                raise SandboxTimeoutError(f"进程沙箱超时（{self.timeout}s）") from e

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise SandboxExecutionError(f"代码执行失败（exit={proc.returncode}）: {stderr[:200]}")
        logger.info("process_sandbox_ok", exit_code=proc.returncode)
        return stdout

    async def _run_unix(self, code: str) -> str:
        """Unix 进程隔离执行。

        rlimit 限制内存+进程数，unshare 禁用网络（若支持）。
        """
        with tempfile.TemporaryDirectory(prefix="orbit-sandbox-") as td:
            script = Path(td) / "code.py"
            script.write_text(code, encoding="utf-8")

            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(script),
                    cwd=td,
                    env={
                        "PATH": "/usr/bin:/bin",
                        "HOME": td,
                        "TMPDIR": td,
                    },
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    preexec_fn=_drop_privileges,
                )
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except TimeoutError as e:
                raise SandboxTimeoutError(f"进程沙箱超时（{self.timeout}s）") from e

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise SandboxExecutionError(f"代码执行失败（exit={proc.returncode}）: {stderr[:200]}")
        logger.info("process_sandbox_ok", exit_code=proc.returncode)
        return stdout


def _drop_privileges() -> None:
    """子进程 preexec_fn：降低权限 + 资源限制。

    WHY preexec_fn 而非父进程设置：preexec_fn 在 fork 后 exec 前执行，
    只影响子进程，不污染父进程。

    import resource / ctypes 在此函数内部——Unix 专有模块，
    Windows 上此函数永不被调用（_run_unix 仅在非 win32 时调用）。
    """
    # mypy 在 Windows 上找不到 resource 模块的属性，全部 suppress。
    import resource  # type: ignore[import-untyped,unused-ignore]

    # 内存限制 256MB（防止 OOM）
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))  # type: ignore[attr-defined]

    # 进程数限制
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))  # type: ignore[attr-defined]

    # 网络隔离（Linux unshare，macOS 不支持则静默跳过）
    try:
        import ctypes

        CLONE_NEWNET = 0x40000000  # Linux 专有
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if libc.unshare(CLONE_NEWNET) != 0:
            pass  # 无 CAP_SYS_ADMIN 时静默失败（非 root）
    except (OSError, AttributeError):
        pass
