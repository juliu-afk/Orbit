"""L4 静态类型检查器（Step 4.1）。

WHY L4：LLM 生成代码常犯类型错误（参数类型与返回值类型不匹配），
这些错误在运行前就能通过 mypy 静态分析发现，拦截成本低。

实现：通过 subprocess 调用 mypy --strict 检查生成的代码。
ADR 决议：使用 --strict 但忽略 no-untyped-def（允许动态函数未标注类型）。

输出解析：mypy 返回非零退出码时，从 stdout 提取错误行号和消息。
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import structlog

from orbit.hallucination.schemas import (
    HallucinationLevel,
    ValidationResult,
)

logger = structlog.get_logger()

# mypy 忽略的规则（PRD Q2 决议：strict 模式但放行未标注类型的函数）
_MYPY_FLAGS = ["--strict", "--disable-error-code", "no-untyped-def"]


class L4TypeValidator:
    """L4 mypy 静态类型检查器。

    用法：
        validator = L4TypeValidator()
        result = await validator.validate(code)
        if not result.passed:
            raise TypeCheckError(result.errors)
    """

    def __init__(self, mypy_path: str = "mypy"):
        self._mypy_path = mypy_path
        self._available: bool | None = None  # 缓存 mypy 可用性

    async def validate(self, code: str) -> ValidationResult:
        """对代码片段运行 mypy 静态类型检查。

        Args:
            code: LLM 生成的 Python 代码

        Returns:
            ValidationResult：passed=True 无类型错误，passed=False 含错误列表
        """
        # 边缘情况：空代码跳过
        if not code.strip():
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L4_TYPE,
                warnings=["empty code, skipped"],
            )

        # 检查 mypy 是否可用（缓存结果）
        available = await self._check_available()
        if not available:
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=["mypy is not installed or not found in PATH"],
            )

        # 写临时文件（mypy 需文件输入，不支持 stdin）
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = Path(f.name)

        try:
            return await self._run_mypy(tmp_path)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as e:
                logger.debug("temp_cleanup_failed", path=str(tmp_path), error=str(e))

    async def _run_mypy(self, file_path: Path) -> ValidationResult:
        """执行 mypy 并解析输出。"""
        cmd = [self._mypy_path, *_MYPY_FLAGS, str(file_path)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError:
            logger.warning("l4_mypy_timeout")
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=["mypy execution timed out (30s)"],
            )
        except FileNotFoundError:
            self._available = False
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=[f"mypy executable not found: {self._mypy_path}"],
            )
        except Exception as e:
            logger.warning("l4_mypy_error", error=str(e))
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L4_TYPE,
                errors=[f"mypy execution failed: {e}"],
            )

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode == 0:
            return ValidationResult(passed=True, level=HallucinationLevel.L4_TYPE)

        # 解析 mypy 输出提取错误行（过滤空行和 summary 行）
        error_lines = [
            line.strip()
            for line in stdout.splitlines()
            if line.strip() and not line.startswith("Found ") and ":" in line
        ]
        if not error_lines:
            error_lines = [stderr.strip()] if stderr.strip() else ["mypy check failed"]

        logger.info("l4_type_error_found", count=len(error_lines))
        return ValidationResult(
            passed=False,
            level=HallucinationLevel.L4_TYPE,
            errors=error_lines[:10],  # 取前 10 条，避免错误过多
            metadata={"error_count": len(error_lines)},
        )

    async def _check_available(self) -> bool:
        """检查 mypy 是否可用（缓存结果避免重复检测）。"""
        if self._available is not None:
            return self._available
        self._available = shutil.which(self._mypy_path) is not None
        if not self._available:
            logger.debug("l4_mypy_not_found", path=self._mypy_path)
        return self._available
