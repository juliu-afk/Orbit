"""L7 沙箱运行时执行验证器（Step 4.2）。

WHY L7：前六层都是静态分析，L7 在沙箱中实际运行代码，用 pytest 风格断言
验证基本功能正确性。这是最接近"真实使用"的验证手段。

实现：将用户代码包装为可执行脚本，末尾加 assert 语句，在 Sandbox 内执行。
若沙箱返回非零退出码 → 运行时错误 → passed=False。
"""

from __future__ import annotations

import structlog

from orbit.hallucination.base import skip_if_empty
from orbit.hallucination.schemas import HallucinationLevel, ValidationResult
from orbit.sandbox.executor import Sandbox, SandboxExecutionError

logger = structlog.get_logger("orbit.hallucination.l7")


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

    @skip_if_empty
    async def validate(self, code: str, assertions: list[str] | None = None) -> ValidationResult:
        """在沙箱中执行代码 + assert 语句。

        Args:
            code: LLM 生成的代码
            assertions: assert 表达式列表（如 ["add(1,2) == 3", "add(-1,1) == 0"]）

        Returns:
            ValidationResult(passed=False) 若 assert 失败或执行异常
        """

        if not await self._sandbox.is_available():
            # P0-7 (Issue#126): sandbox 不可用时不应 fail-open——
            # 无法验证 = 不应信任
            # P2-6 (PR#133): CI/开发环境无 Docker 时所有代码被标记"需人工审查"——
            # 调用方应提供 ENABLE_L7 配置开关，无沙箱时跳过 L7 而非 fail
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L7_RUNTIME,
                errors=["Sandbox 不可用——无法执行 L7 运行时验证"],
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
            # P0-7 (Issue#126): 非 SandboxExecutionError 的异常也应 fail-closed——
            # 无法区分是代码 bug 还是沙箱基础设施问题时，不应静默通过
            logger.warning("l7_sandbox_error", error=str(e))
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L7_RUNTIME,
                errors=[f"L7 执行异常: {e}"],
                metadata={"execution_error": str(e)},
            )

        logger.info("l7_runtime_ok", assertion_count=len(assertions or []))
        return ValidationResult(
            passed=True,
            level=HallucinationLevel.L7_RUNTIME,
            metadata={"assertions": assertions or [], "all_passed": True},
        )
