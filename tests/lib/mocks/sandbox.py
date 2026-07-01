"""Mock 沙箱——替代 sandbox/executor.py:Sandbox。

可配置 exit_code/stdout/stderr/超时/OOM/权限拒绝。
用于单元测试中替代 Docker 隔离执行，不触发真实容器。
"""

from __future__ import annotations

import asyncio

from orbit.sandbox.executor import SandboxError, SandboxExecutionError, SandboxTimeoutError


class MockSandbox:
    """Mock 沙箱——替代 sandbox/executor.py:Sandbox。100% 兼容 Sandbox.run() 接口签名。"""

    def __init__(
        self,
        exit_code: int = 0,
        stdout: str = "OK",
        stderr: str = "",
        timeout_seconds: int | None = None,
        oom: bool = False,
        permission_denied: bool = False,
    ) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timeout_seconds = timeout_seconds
        self.oom = oom
        self.permission_denied = permission_denied
        self.call_count: int = 0
        self.calls: list[dict] = []

    def with_result(self, exit_code: int = 0, stdout: str = "OK", stderr: str = "") -> "MockSandbox":
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        return self

    def with_timeout(self, seconds: int) -> "MockSandbox":
        self.timeout_seconds = seconds
        return self

    def with_oom(self) -> "MockSandbox":
        self.oom = True
        return self

    def with_permission_denied(self) -> "MockSandbox":
        self.permission_denied = True
        return self

    async def run(self, code: str, language: str = "python", external_paths: list[str] | None = None) -> str:
        self.call_count += 1
        self.calls.append({"code": code, "language": language, "external_paths": external_paths})

        if language != "python":
            raise SandboxError(f"MVP 仅支持 python，不支持 {language}")

        if self.timeout_seconds is not None:
            await asyncio.sleep(min(self.timeout_seconds, 0.1))
            raise SandboxTimeoutError(f"沙箱执行超时（{self.timeout_seconds}s）")

        if self.oom:
            raise SandboxError("OOM: container killed by OOM killer")

        if self.permission_denied:
            raise SandboxExecutionError("代码执行失败（exit=1）: Permission denied")

        if self.exit_code != 0:
            raise SandboxExecutionError(f"代码执行失败（exit={self.exit_code}）: {self.stderr[:200]}")

        return self.stdout

    async def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        self.call_count = 0
        self.calls.clear()
