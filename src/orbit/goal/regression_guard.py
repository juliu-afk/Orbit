"""RegressionGuard——每个 PR 合入后跑全量回归测试。

WHY 每 PR 合入后立即回归: 一个子任务的修改可能破坏另一个子任务的功能。
尽早发现 → 回退 PR → 修复 → 重新合入。
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger("orbit.goal")


class RegressionResult:
    """回归测试结果。"""

    def __init__(
        self,
        passed: bool = True,
        total_tests: int = 0,
        failed_tests: int = 0,
        output_tail: str = "",
        duration_s: float = 0.0,
    ) -> None:
        self.passed = passed
        self.total_tests = total_tests
        self.failed_tests = failed_tests
        self.output_tail = output_tail
        self.duration_s = duration_s


class RegressionGuard:
    """回归守卫——每 PR 合入后全量测试。

    Usage:
        guard = RegressionGuard(verifier, test_commands=["pytest tests/ -q"])
        result = await guard.check()
        if not result.passed:
            # 回退 PR
    """

    def __init__(
        self,
        verifier: Any = None,  # ExecutorVerifier
        test_commands: list[str] | None = None,
    ) -> None:
        self._verifier = verifier
        self._commands = test_commands or ["pytest tests/ -q"]

    async def check(self) -> RegressionResult:
        """执行全量回归测试。

        Returns:
            RegressionResult: passed + test count + output
        """
        if not self._verifier:
            logger.info("regression_guard_mock_mode")
            return RegressionResult(passed=True)

        try:
            import time

            started = time.time()
            result = await self._verifier.execute(self._commands)
            elapsed = time.time() - started

            total = result.total_count
            failed = len(result.failed_commands)

            passed = result.all_passed
            if not passed:
                logger.warning(
                    "regression_failed",
                    failed_commands=failed,
                    total_commands=total,
                    output=(
                        result.failed_commands[0].get("stderr_tail", "")[:200]
                        if result.failed_commands
                        else ""
                    ),
                )

            return RegressionResult(
                passed=passed,
                total_tests=total,
                failed_tests=failed,
                output_tail=result.to_prompt_section(),
                duration_s=elapsed,
            )
        except Exception as e:
            logger.error("regression_guard_error", error=str(e))
            return RegressionResult(passed=False, output_tail=str(e))
