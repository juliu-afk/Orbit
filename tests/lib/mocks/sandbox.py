"""Mock 沙箱——替代 sandbox/executor.py:Sandbox。

可配置 exit_code/stdout/stderr/超时/OOM/权限拒绝。
用于单元测试中替代 Docker 隔离执行，不触发真实容器。

使用示例:
    # 正常执行
    mock = MockSandbox(stdout="SUCCESS")
    # 超时
    mock = MockSandbox(timeout_seconds=1)
    # 权限拒绝
    mock = MockSandbox(permission_denied=True)
"""

from __future__ import annotations

import asyncio


# 复用生产异常类（不修改异常层次）
from orbit.sandbox.executor import (
    SandboxError,
    SandboxExecutionError,
    SandboxTimeoutError,
)


class MockSandbox:
    """Mock 沙箱——替代 sandbox/executor.py:Sandbox。

    100% 兼容 Sandbox.run() 接口签名。不启动 Docker 容器。
    """

    def __init__(
        self,
        exit_code: int = 0,
        stdout: str = "OK",
        stderr: str = "",
        timeout_seconds: int | None = None,
        oom: bool = False,
        permission_denied: bool = False,
    ) -> None:
        """初始化 Mock 沙箱。

        Args:
            exit_code: 模拟退出码（0=成功）
            stdout: 标准输出内容
            stderr: 标准错误输出内容
            timeout_seconds: 模拟超时秒数（None=不超时）
            oom: True → 抛出 OOM SandboxError
            permission_denied: True → 抛出 SandboxExecutionError("Permission denied")
        """
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timeout_seconds = timeout_seconds
        self.oom = oom
        self.permission_denied = permission_denied

        # 调用追踪
        self.call_count: int = 0
        self.calls: list[dict] = []  # 每次调用的 code/language 参数

    # ── 链式配置方法 ──────────────────────────────────────

    def with_result(self, exit_code: int = 0, stdout: str = "OK", stderr: str = "") -> "MockSandbox":
        """设置执行结果。"""
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        return self

    def with_timeout(self, seconds: int) -> "MockSandbox":
        """设置超时秒数。"""
        self.timeout_seconds = seconds
        return self

    def with_oom(self) -> "MockSandbox":
        """触发 OOM 错误。"""
        self.oom = True
        return self

    def with_permission_denied(self) -> "MockSandbox":
        """触发权限拒绝错误。"""
        self.permission_denied = True
        return self

    # ── 生产接口兼容方法 ──────────────────────────────────

    async def run(
        self,
        code: str,
        language: str = "python",
        external_paths: list[str] | None = None,
    ) -> str:
        """Mock 代码执行——100% 兼容 Sandbox.run() 签名。

        Returns:
            stdout 字符串

        Raises:
            SandboxTimeoutError: timeout_seconds 设置时
            SandboxError: oom=True 时
            SandboxExecutionError: permission_denied 或 exit_code≠0 时
        """
        self.call_count += 1
        self.calls.append({"code": code, "language": language, "external_paths": external_paths})

        # 语言校验（与生产 Sandbox 一致）
        if language != "python":
            raise SandboxError(f"MVP 仅支持 python，不支持 {language}")

        # 超时模拟
        if self.timeout_seconds is not None:
            await asyncio.sleep(min(self.timeout_seconds, 0.1))  # 测试中不真等
            raise SandboxTimeoutError(f"沙箱执行超时（{self.timeout_seconds}s）")

        # OOM 模拟
        if self.oom:
            raise SandboxError("OOM: container killed by OOM killer")

        # 权限拒绝模拟
        if self.permission_denied:
            raise SandboxExecutionError("代码执行失败（exit=1）: Permission denied")

        # 非零退出码模拟
        if self.exit_code != 0:
            raise SandboxExecutionError(f"代码执行失败（exit={self.exit_code}）: {self.stderr[:200]}")

        return self.stdout

    async def is_available(self) -> bool:
        """Mock Docker 可用性检测——始终返回 True。"""
        return True

    def reset(self) -> None:
        """重置调用追踪状态。"""
        self.call_count = 0
        self.calls.clear()
