"""防幻觉层基类——内部减熵 P2.

抽取 5 个防幻觉层重复的 guard 装饰器.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from orbit.hallucination import HallucinationLevel, ValidationResult


def skip_if_empty(func: Callable) -> Callable:
    """代码为空时跳过验证——返回 passed=True 的 ValidationResult."""

    @functools.wraps(func)
    def wrapper(self: Any, code: str, *args: Any, **kwargs: Any) -> ValidationResult:
        if not code.strip():
            return ValidationResult(
                passed=True,
                level=self.level,
                warnings=["empty code, skipped"],
            )
        return func(self, code, *args, **kwargs)

    return wrapper


def skip_if_no_sandbox(func: Callable) -> Callable:
    """沙箱不可用时跳过验证."""

    @functools.wraps(func)
    async def wrapper(self: Any, code: str, *args: Any, **kwargs: Any) -> ValidationResult:
        sandbox = getattr(self, "_sandbox", None)
        if sandbox and not await sandbox.is_available():
            return ValidationResult(
                passed=True,
                level=self.level,
                warnings=["sandbox unavailable, skipped"],
            )
        return await func(self, code, *args, **kwargs)

    return wrapper


class BaseValidator:
    """防幻觉层公共基类——提供 level 属性供装饰器使用."""

    level: HallucinationLevel
