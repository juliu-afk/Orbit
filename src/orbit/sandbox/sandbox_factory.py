"""沙箱工厂——Docker → ProcessSandbox → 拒绝启动。

WHY 工厂而非直接实例化：Orbit 在启动时必须确认有可用沙箱，
无隔离 = 不安全 = 拒绝运行。工厂集中此检查逻辑。
"""

from __future__ import annotations

import structlog

from orbit.sandbox.executor import Sandbox
from orbit.sandbox.process_sandbox import ProcessSandbox

logger = structlog.get_logger("orbit.sandbox.factory")

# 硬停止错误信息——所有沙箱机制均不可用时的提示
NO_SANDBOX_MESSAGE = (
    "无可用沙箱隔离机制。"
    "请安装 Docker 或启用 Windows AppContainer。"
    "系统无法在不安全环境运行。"
)


async def create_sandbox(
    docker_timeout: int | None = None,
) -> Sandbox | ProcessSandbox:
    """按优先级选择沙箱。

    1. Docker Engine 可用 → DockerSandbox（容器级隔离）
    2. Docker 不可用 → ProcessSandbox（进程级隔离）
    3. 全部不可用 → RuntimeError（拒绝启动）

    Returns:
        Sandbox 或 ProcessSandbox 实例
    Raises:
        RuntimeError: 无可用沙箱机制
    """
    # L1: Docker
    docker = Sandbox() if docker_timeout is None else Sandbox(timeout=docker_timeout)
    if await docker.is_available():
        logger.info("sandbox_mode", mode="Docker", isolation="container")
        return docker

    logger.warning("sandbox_docker_unavailable", fallback="ProcessSandbox")

    # L2: ProcessSandbox
    process = ProcessSandbox() if docker_timeout is None else ProcessSandbox(timeout=docker_timeout)
    if await process.is_available():
        logger.warning("sandbox_mode", mode="ProcessSandbox", isolation="process")
        return process

    # L3: 硬停止
    logger.error("sandbox_none_available")
    raise RuntimeError(NO_SANDBOX_MESSAGE)
