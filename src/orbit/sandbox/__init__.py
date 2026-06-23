"""沙箱模块——代码隔离执行。

DockerSandbox（L1 主方案）：容器级隔离，Docker Engine 依赖。
ProcessSandbox（L2 兜底）：进程级隔离，零外部依赖。
sandbox_factory：自动选择可用沙箱，全部不可用时拒绝启动。
"""

from orbit.sandbox.executor import (
    Sandbox,
    SandboxError,
    SandboxExecutionError,
    SandboxTimeoutError,
)
from orbit.sandbox.process_sandbox import ProcessSandbox
from orbit.sandbox.sandbox_factory import NO_SANDBOX_MESSAGE, create_sandbox

__all__ = [
    "NO_SANDBOX_MESSAGE",
    "ProcessSandbox",
    "Sandbox",
    "SandboxError",
    "SandboxExecutionError",
    "SandboxTimeoutError",
    "create_sandbox",
]
