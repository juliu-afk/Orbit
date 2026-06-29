"""依赖膨胀拦截——业务层减熵 P2.

Agent 提议安装新包时检查已有替代方案.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("orbit.dependency_guard")

# P2: 常见可被标准库/已有包替代的依赖
STD_LIB_ALTERNATIVES: dict[str, str] = {
    "fuzzywuzzy": "difflib（标准库）",
    "python-levenshtein": "difflib（标准库）",
    "schedule": "标准库 sched 模块",
    "requests": "httpx（项目已有）或 urllib（标准库）",
    "nose": "pytest（项目已有）",
    "pathlib2": "pathlib（标准库 Python 3.4+）",
    "mock": "unittest.mock（标准库 Python 3.3+）",
    "six": "无需——项目仅支持 Python 3.11+",
}


@dataclass
class DependencyCheck:
    """依赖检查结果."""

    package: str
    stdlib_alternative: str = ""
    existing_alternative: str = ""
    transitive_count: int = 0
    warnings: list[str] = field(default_factory=list)
    recommendation: str = ""
    needs_confirmation: bool = False


class DependencyGuard:
    """Agent 提议新增依赖时的拦截检查.

    用法:
        guard = DependencyGuard()
        check = await guard.check("fuzzywuzzy", "需要模糊匹配")
        if check.needs_confirmation:
            print(f"建议: {check.recommendation}")
    """

    async def check(self, proposed_package: str, reason: str = "") -> DependencyCheck:
        """检查提议的依赖.

        Returns:
            DependencyCheck——若 needs_confirmation=True 则拦截
        """
        result = DependencyCheck(package=proposed_package)

        # 检查 1: 标准库替代
        std_alt = STD_LIB_ALTERNATIVES.get(proposed_package)
        if std_alt:
            result.stdlib_alternative = std_alt
            result.recommendation = f"建议用 {std_alt} 替代 {proposed_package}"
            result.needs_confirmation = True
            return result

        # 检查 2: 无已知替代——放行
        return result
