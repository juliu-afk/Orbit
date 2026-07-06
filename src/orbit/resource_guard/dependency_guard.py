"""依赖膨胀拦截——业务层减熵 P2.

Agent 提议安装新包时检查已有替代方案.
"""

from __future__ import annotations

import json as _json
import urllib.request as _urllib
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("orbit.dependency_guard")

# P2-3: PyPI JSON API 基础 URL
_PYPI_API = "https://pypi.org/pypi"
# PyPI 查询超时（秒）
_PYPI_TIMEOUT = 5

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

    # P2-1/P2-2: 已知传递依赖数量（典型包 → 传递依赖数）
    _TRANSITIVE_COUNTS: dict[str, int] = {
        "fuzzywuzzy": 0,  # 纯 Python, 0 传递依赖
        "python-levenshtein": 1,  # 依赖 C 扩展
        "schedule": 0,
        "requests": 5,  # urllib3+certifi+charset_normalizer+idna+h11
    }

    def check(self, proposed_package: str, reason: str = "") -> DependencyCheck:
        """检查提议的依赖——硬编码字典优先，未命中则查 PyPI API (P2-3)."""
        result = DependencyCheck(package=proposed_package)

        # 检查 1: 标准库替代（硬编码字典）
        std_alt = STD_LIB_ALTERNATIVES.get(proposed_package)
        if std_alt:
            result.stdlib_alternative = std_alt
            result.recommendation = f"建议用 {std_alt} 替代 {proposed_package}"
            result.needs_confirmation = True
            return result

        # 检查 2: 传递依赖数量（硬编码字典优先）
        transitive = self._TRANSITIVE_COUNTS.get(proposed_package, -1)
        if transitive >= 0:
            result.transitive_count = transitive
            if transitive > 3:
                result.warnings.append(f"将新增 {transitive} 个传递依赖")
                result.needs_confirmation = True
            return result

        # P2-3: 硬编码未命中 → PyPI API 实时查询
        pypi_info = self._fetch_pypi_info(proposed_package)
        if pypi_info:
            requires = pypi_info.get("requires_dist") or []
            if len(requires) > 3:
                result.transitive_count = len(requires)
                result.warnings.append(
                    f"{proposed_package} 有 {len(requires)} 个传递依赖"
                )
                result.needs_confirmation = True

        return result

    def _fetch_pypi_info(self, package: str) -> dict | None:
        """查询 PyPI JSON API——获取包元数据 (P2-3).

        PyPI API 免费、无需认证。超时/不可达时降级返回 None。
        """
        try:
            url = f"{_PYPI_API}/{package}/json"
            req = _urllib.Request(url, headers={"User-Agent": "Orbit/0.36"})
            with _urllib.urlopen(req, timeout=_PYPI_TIMEOUT) as resp:
                return _json.loads(resp.read().decode())
        except Exception as e:
            logger.debug("pypi_api_fetch_failed", package=package, error=str(e))
            return None
