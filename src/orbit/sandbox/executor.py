"""MVP-03 Docker 沙箱原型 + Session PR #2 多卷挂载。

WHY 沙箱：LLM 生成的代码必须隔离执行，禁止宿主机直接跑（安全 + 可重复）。
Docker 隔离：每个代码片段在独立容器内执行，超时强杀，输出捕获，用后即删。

Session PR #2 改动：挂载策略从单临时文件 → 项目路径多卷挂载。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import structlog

from orbit.core.config import settings

logger = structlog.get_logger("orbit.sandbox.executor")

# MVP 用 Python 官方镜像（生产可换更小的 python:slim/alpine）
DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT = settings.SANDBOX_TIMEOUT_SECONDS
MAX_READONLY_MOUNTS = 5  # Session PR #2: 最多挂载 5 个只读项目路径


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

    Session PR #2: 支持项目路径绑定（rw）和其他项目只读挂载（ro）。
    """

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        timeout: int = DEFAULT_TIMEOUT,
        project_path: str = "",
        readonly_paths: list[str] | None = None,
    ):
        """
        Args:
            project_path: 当前项目路径 → 挂载为 /workspace:rw
            readonly_paths: 其他项目路径列表 → 挂载为 /readonly/{name}:ro
        """
        self.image = image
        self.timeout = timeout
        self.project_path = project_path
        self.readonly_paths = readonly_paths or []
        # WHY 运行时检测 Docker：避免在无 Docker 环境（CI/测试）import 时就失败
        self._docker_available: bool | None = None

    async def run(
        self,
        code: str,
        language: str = "python",
        external_paths: list[str] | None = None,
    ) -> str:
        """执行代码片段，返回 stdout。

        Args:
            code: 代码内容
            language: 语言（MVP 仅支持 python，其他抛错）
            external_paths: LLM 代码引用的外部路径（Session PR #2）

        Raises:
            SandboxTimeoutError: 超时
            SandboxExecutionError: 非零退出码
            SandboxError: Docker 不可用/其他错误
        """
        if language != "python":
            raise SandboxError(f"MVP 仅支持 python，不支持 {language}")

        if not await self.is_available():
            raise SandboxError("Docker 不可用。测试请 mock run()，生产需 Docker Engine")

        # 代码写临时文件，挂载到容器
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            host_script = Path(f.name)

        try:
            return await self._run_in_container(host_script, external_paths=external_paths)
        finally:
            # 清理临时文件（防止泄漏）
            try:
                host_script.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("temp_cleanup_failed", path=str(host_script), error=str(e))

    def _build_mounts(
        self, host_script: Path, external_paths: list[str] | None = None
    ) -> list[str]:
        """生成 docker run -v 参数列表（Session PR #2）。

        挂载顺序:
          1. 临时脚本 → /tmp/xxx.py:ro
          2. 绑定项目路径 → /workspace:rw
          3. 其他已注册项目 → /readonly/{name}:ro（最多 MAX_READONLY_MOUNTS 个）
          4. 外部引用路径 → /readonly/ext_{i}:ro（最多 MAX_READONLY_MOUNTS 个）

        WHY ro 而非 rw: 防止沙箱内代码写越界到其他项目或外部路径。
        WHY _to_docker_path 对 host_script: Windows Docker Desktop 需要 //d/ 格式，
        与项目路径挂载一致的路径格式避免环境差异导致挂载失败。
        """
        docker_script = _to_docker_path(str(host_script))
        mounts = [f"{docker_script}:/tmp/{host_script.name}:ro"]

        # 绑定项目路径 → 读写
        if self.project_path and os.path.isdir(self.project_path):
            docker_path = _to_docker_path(self.project_path)
            mounts.append(f"{docker_path}:/workspace:rw")

        # 其他已注册项目 → 只读
        for i, rp in enumerate(self.readonly_paths[:MAX_READONLY_MOUNTS]):
            if os.path.isdir(rp) and rp != self.project_path:
                name = Path(rp).name or f"proj_{i}"
                docker_path = _to_docker_path(rp)
                mounts.append(f"{docker_path}:/readonly/{name}:ro")

        # 外部引用路径 → 只读（已实质废弃——仅允许 workspace 内路径）
        # P0-11 (Issue#126): commonpath 校验有效封闭了外部路径
        # P1-2 (PR#133): external_paths 现只能挂载 workspace 内路径——
        # 与 readonly_paths 冗余。保留参数签名兼容，语义已变。
        # 紧急需要外部路径时：设置 SANDBOX_ALLOWED_EXTERNAL_PATHS 环境变量
        # 格式：分号或逗号分隔的绝对路径列表，例 "C:/shared;/tmp/lib"
        _allowed_external = self._parse_external_allowlist()
        ext_paths = external_paths or []
        _readonly_resolved = {os.path.realpath(p) for p in self.readonly_paths}
        for i, ep in enumerate(ext_paths[:MAX_READONLY_MOUNTS]):
            _resolved = os.path.realpath(ep)
            if not os.path.isdir(_resolved) or _resolved in _readonly_resolved:
                continue
            # 路径遍历检测——禁止 ../ 和符号链接逃逸
            # 例外：SANDBOX_ALLOWED_EXTERNAL_PATHS 白名单中的路径允许挂载
            _workspace = os.path.realpath(self.project_path) if self.project_path else None
            if _workspace and os.path.commonpath([_workspace, _resolved]) != _workspace:
                if _resolved in _allowed_external:
                    logger.info("sandbox_external_path_allowed", path=ep)
                else:
                    logger.warning("sandbox_external_path_blocked", path=ep, resolved=_resolved)
                    continue
            name = Path(_resolved).name or f"ext_{i}"
            docker_path = _to_docker_path(_resolved)
            mounts.append(f"{docker_path}:/readonly/ext/{name}:ro")

        return mounts

    @staticmethod
    def _parse_external_allowlist() -> set[str]:
        """解析 SANDBOX_ALLOWED_EXTERNAL_PATHS 环境变量。

        格式：分号或逗号分隔的绝对路径列表（Windows 兼容两种分隔符）。
        每个路径会被 realpath 解析以消除符号链接。

        用途：紧急需要沙箱访问外部路径时（如共享库目录），
        通过环境变量授权，避免修改代码。
        """
        raw = os.getenv("SANDBOX_ALLOWED_EXTERNAL_PATHS", "")
        if not raw.strip():
            return set()
        paths = []
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part and os.path.isabs(part):
                try:
                    paths.append(os.path.realpath(part))
                except OSError:
                    pass  # 路径不可达——静默跳过
        return set(paths)

    async def _run_in_container(
        self, host_script: Path, external_paths: list[str] | None = None
    ) -> str:
        """在 Docker 容器内执行脚本。"""
        container_script = f"/tmp/{host_script.name}"  # nosec B108: 容器内路径，非宿主机
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",  # WHY 网络隔离：LLM 代码不应访问网络（防数据外泄）
        ]
        # Session PR #2: 多卷挂载
        for mount in self._build_mounts(host_script, external_paths=external_paths):
            cmd.extend(["-v", mount])

        cmd.extend([self.image, "python", container_script])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except TimeoutError as e:
            raise SandboxTimeoutError(f"沙箱执行超时（{self.timeout}s）") from e

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        if exit_code != 0:
            logger.warning(
                "sandbox_nonzero_exit",
                exit_code=exit_code,
                stderr=stderr[:500],
            )
            raise SandboxExecutionError(f"代码执行失败（exit={exit_code}）: {stderr[:200]}")
        logger.info("sandbox_exec_ok", exit_code=exit_code, stdout_len=len(stdout))
        return stdout

    async def is_available(self) -> bool:
        """检测 Docker 是否可用（缓存结果，3s 超时）。"""
        if self._docker_available is not None:
            return self._docker_available
        docker_path = shutil.which("docker")
        if docker_path is None:
            self._docker_available = False
            return False
        # WHY docker version 而非 info: version 更快，且 Docker 在运行则 <1s 响应
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_path,
                "version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=3)
            self._docker_available = proc.returncode == 0
        except (TimeoutError, Exception):
            self._docker_available = False
        return self._docker_available


def _to_docker_path(host_path: str) -> str:
    """转换 Windows 路径为 Docker 可识别的格式。

    WHY 路径转换: Windows Docker Desktop 需要特殊路径格式。
    D:/xxx → //d/xxx  (Git Bash / MSYS2 兼容)
    C:/xxx → //c/xxx
    """
    if os.name == "nt":
        # Windows: D:/Code → //d/Code
        drive = host_path[0].lower()
        rest = host_path[2:].replace("\\", "/")
        return f"//{drive}{rest}"
    return host_path
