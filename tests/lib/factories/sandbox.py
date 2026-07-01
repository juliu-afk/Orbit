"""沙箱工厂——创建测试用沙箱执行结果。

用于快速构造 SandboxResult dict，不依赖真实 Docker。
"""

from __future__ import annotations

from typing import Any


def create_sandbox_result(
    exit_code: int = 0,
    stdout: str = "OK",
    stderr: str = "",
    duration_ms: int = 150,
    **kwargs: Any,
) -> dict[str, Any]:
    """创建沙箱执行结果 dict。

    Args:
        exit_code: 退出码（0=成功）
        stdout: 标准输出
        stderr: 标准错误输出
        duration_ms: 执行耗时（毫秒）
    """
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        **kwargs,
    }
