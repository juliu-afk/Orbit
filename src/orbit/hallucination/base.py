"""防幻觉层基类——内部减熵 P2.

抽取 5 个防幻觉层重复的 guard 装饰器。

WHY 不在此文件顶层 import HallucinationLevel/ValidationResult:
  hallucination/__init__.py → l1_graph → base → schemas 形成循环导入。
  改为在函数内惰性导入，避免模块级循环依赖。
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orbit.hallucination.schemas import HallucinationLevel, ValidationResult


def skip_if_empty(func: Callable) -> Callable:
    """代码为空时跳过验证——返回 passed=True 的 ValidationResult.

    WHY 惰性导入 HallucinationLevel/ValidationResult:
    避免 hallucination/__init__.py → l1_graph → base → schemas 循环导入。
    level 默认 L1_GRAPH——装饰器只用于提前返回，真实 level 由 validate 设置。
    """

    @functools.wraps(func)
    async def wrapper(self: Any, code: str, *args: Any, **kwargs: Any) -> Any:
        if not code.strip():
            from orbit.hallucination.schemas import HallucinationLevel, ValidationResult  # noqa: F811
            return ValidationResult(
                passed=True,
                level=HallucinationLevel.L1_GRAPH,
                warnings=["empty code, skipped"],
            )
        return await func(self, code, *args, **kwargs)

    return wrapper


def skip_if_no_sandbox(func: Callable) -> Callable:
    """沙箱不可用时跳过验证."""

    @functools.wraps(func)
    async def wrapper(self: Any, code: str, *args: Any, **kwargs: Any) -> Any:
        sandbox = getattr(self, "sandbox", None)
        if sandbox is None:
            from orbit.hallucination.schemas import ValidationResult  # noqa: F811
            return ValidationResult(passed=True, warnings=["sandbox not available, skipped"])
        return await func(self, code, *args, **kwargs)

    return wrapper


class BaseValidator:
    """验证器基类——提供 level 属性供装饰器使用."""

    level: Any = None  # HallucinationLevel，子类覆盖
