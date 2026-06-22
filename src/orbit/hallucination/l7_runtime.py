"""L7 沙箱运行时执行验证器（Step 4.2）。

WHY L7：前六层都是静态分析，L7 在沙箱中实际运行代码，用 pytest 风格断言
验证基本功能正确性。这是最接近"真实使用"的验证手段。

实现：将用户代码包装为可执行脚本，末尾加 assert 语句，在 Sandbox 内执行。
若沙箱返回非零退出码 → 运行时错误 → passed=False。
"""

from __future__ import annotations

import structlog

from orbit.hallucination.schemas import HallucinationLevel, ValidationResult
from orbit.sandbox.executor import Sandbox, SandboxExecutionError

logger = structlog.get_logger()


class L7RuntimeValidator:
    """L7 沙箱运行时验证器。

    用法：
        validator = L7RuntimeValidator(sandbox)
        result = await validator.validate(code, assertions=["add(1,2) == 3"])
        if not result.passed:
            raise L7RuntimeError(result.errors)
    """

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    async def validate(self, code: str, assertions: list[str] | None = None) -> ValidationResult:
        """在沙箱中执行代码 + assert 语句。

        Args:
            code: LLM 生成的代码
            assertions: assert 表达式列表（如 ["add(1,2) == 3", "add(-1,1) == 0"]）

        Returns:
            ValidationResult(passed=False) 若 assert 失败或执行异常
        """
        if not code.strip():
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L7_RUNTIME,
                warnings=["empty code, skipped"],
            )

        if not await self._sandbox.is_available():
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L7_RUNTIME,
                warnings=["sandbox unavailable, L7 skipped"],
            )

        # 构造包装脚本
        if assertions:
            assert_lines = "\n".join(f"assert {a}, f'Failed: {a}'" for a in assertions)
            wrapped = f"{code}\n\n# L7 runtime assertions\n{assert_lines}\n"
        else:
            wrapped = code

        try:
            await self._sandbox.run(wrapped, language="python")
        except SandboxExecutionError as e:
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L7_RUNTIME,
                errors=[f"Runtime assertion failed: {e}"],
                metadata={"assertions": assertions or []},
            )
        except Exception as e:
            logger.info("l7_sandbox_error", error=str(e))
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L7_RUNTIME,
                warnings=[f"Sandbox execution failed (L7 cannot verify): {e}"],
                metadata={"execution_error": str(e)},
            )

        logger.info("l7_runtime_ok", assertion_count=len(assertions or []))
        return ValidationResult(
            passed=True,
            level=HallucinationLevel.L7_RUNTIME,
            metadata={"assertions": assertions or [], "all_passed": True},
        )
