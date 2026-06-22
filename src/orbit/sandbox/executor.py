"""MVP-03 Docker 沙箱原型。

WHY 沙箱：LLM 生成的代码必须隔离执行，禁止宿主机直接跑（安全 + 可重复）。
Docker 隔离：每个代码片段在独立容器内执行，超时强杀，输出捕获，用后即删。

生产级沙箱（Step 5.x）会加：资源限制（cgroup）、网络隔离、预热池。
MVP 阶段实现最小可用：docker run --rm + 超时 + 输出捕获。
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path

import structlog

from orbit.core.config import settings

logger = structlog.get_logger()

# MVP 用 Python 官方镜像（生产可换更小的 python:slim/alpine）
DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT = settings.SANDBOX_TIMEOUT_SECONDS


class SandboxError(Exception):
    """沙箱执行错误基类。"""


class SandboxTimeoutError(SandboxError):
    """执行超时。"""


class SandboxExecutionError(SandboxError):
    """代码执行失败（非零退出码）。"""


class Sandbox:
    """Docker 代码片段沙箱。

    被调度器调用（Agent 的 CODING 阶段执行生成代码）。
    被防幻觉层 L5 调用（沙箱执行验证）。
    """

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.image = image
        self.timeout = timeout
        # WHY 运行时检测 Docker：避免在无 Docker 环境（CI/测试）import 时就失败
        self._docker_available: bool | None = None

    async def run(self, code: str, language: str = "python") -> str:
        """执行代码片段，返回 stdout。

        Args:
            code: 代码内容
            language: 语言（MVP 仅支持 python，其他抛错）

        Raises:
            SandboxTimeoutError: 超时
            SandboxExecutionError: 非零退出码
            SandboxError: Docker 不可用/其他错误
        """
        if language != "python":
            raise SandboxError(f"MVP 仅支持 python，不支持 {language}")

        if not await self.is_available():
            raise SandboxError(
                "Docker 不可用。测试请 mock run()，生产需 Docker Engine"
            )

        # 代码写临时文件，挂载到容器
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            host_script = Path(f.name)

        try:
            return await self._run_in_container(host_script)
        finally:
            # 清理临时文件（防止泄漏）
            try:
                host_script.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("temp_cleanup_failed", path=str(host_script), error=str(e))

    async def _run_in_container(self, host_script: Path) -> str:
        """在 Docker 容器内执行脚本。"""
        container_script = f"/tmp/{host_script.name}"
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",  # WHY 网络隔离：LLM 代码不应访问网络（防数据外泄）
            "-v", f"{host_script}:{container_script}:ro",
            self.image,
            "python", container_script,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except asyncio.TimeoutError as e:
            raise SandboxTimeoutError(
                f"沙箱执行超时（{self.timeout}s）"
            ) from e

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        if exit_code != 0:
            logger.warning(
                "sandbox_nonzero_exit",
                exit_code=exit_code,
                stderr=stderr[:500],
            )
            raise SandboxExecutionError(
                f"代码执行失败（exit={exit_code}）: {stderr[:200]}"
            )
        logger.info("sandbox_exec_ok", exit_code=exit_code, stdout_len=len(stdout))
        return stdout

    async def is_available(self) -> bool:
        """检测 Docker 是否可用（缓存结果）。"""
        if self._docker_available is not None:
            return self._docker_available
        # docker 不在 PATH 时返回不可用
        docker_path = shutil.which("docker")
        if docker_path is None:
            self._docker_available = False
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            self._docker_available = proc.returncode == 0
        except Exception as e:
            logger.warning("docker_check_failed", error=str(e))
            self._docker_available = False
        return self._docker_available