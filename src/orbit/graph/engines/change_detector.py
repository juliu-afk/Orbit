"""变更影响检测器——git diff → 受影响符号 + 风险分类。

WHY 独立模块：detect_changes 是调度器任务失效策略的核心输入，
与解析引擎分离便于独立测试和演进。借鉴 CBM detect_changes 设计。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from orbit.graph.engines.code_graph import CodeGraphEngine

logger = structlog.get_logger("orbit.graph.change_detector")


@dataclass
class ChangeImpact:
    """单个受影响的符号 + 风险评估。"""

    name: str
    file_path: str
    risk: str  # high / medium / low
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)


class ChangeDetector:
    """基于 git diff 的变更影响分析。

    用法::

        detector = ChangeDetector(code_graph)
        impacts = await detector.analyze("HEAD~1")
        for imp in impacts:
            print(f"{imp.name}: {imp.risk} risk ({len(imp.callers)} callers)")
    """

    RISK_HIGH_THRESHOLD = 10   # ≥10 调用者 → 高风险
    RISK_MED_THRESHOLD = 1     # 1-9 调用者 → 中风险

    def __init__(self, code_graph: "CodeGraphEngine") -> None:
        self._cg = code_graph

    async def analyze(self, base_ref: str = "HEAD~1") -> list[ChangeImpact]:
        """比较 base_ref..HEAD 的变更，返回受影响符号列表。

        Args:
            base_ref: git 引用——默认 HEAD~1（最近一次 commit vs 当前工作区）

        Returns:
            按风险降序排列的 ChangeImpact 列表。
        """
        changed_files = self._git_diff_files(base_ref)
        if not changed_files:
            return []

        # P0-1 fix: 用 get_all_nodes() 过滤而非 find_definitions_with_positions("")
        # 后者生成 SQL WHERE name='' → 恒返回 [] → 整个检测功能无效
        try:
            all_nodes = await self._cg.get_all_nodes()
        except Exception:
            return []

        impacts: list[ChangeImpact] = []
        for fpath in changed_files:
            file_defs = [n for n in all_nodes if n.get("file_path") == fpath]

            if not file_defs:
                continue

            for d in file_defs:
                name = d.get("name", "")
                try:
                    callers = await self._cg.get_callers(name)
                except Exception:
                    callers = []
                try:
                    callees = await self._cg.get_callees(name)
                except Exception:
                    callees = []

                caller_count = len(callers)
                if caller_count >= self.RISK_HIGH_THRESHOLD:
                    risk = "high"
                elif caller_count >= self.RISK_MED_THRESHOLD:
                    risk = "medium"
                else:
                    risk = "low"

                impacts.append(ChangeImpact(
                    name=name, file_path=fpath, risk=risk,
                    callers=callers[:20], callees=callees[:20],
                ))

        impacts.sort(key=lambda x: len(x.callers), reverse=True)
        logger.info("change_impact_analyzed", files=len(changed_files), impacts=len(impacts))
        return impacts

    def _git_diff_files(self, base_ref: str) -> list[str]:
        """git diff --name-only。"""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref],
                capture_output=True, text=True, timeout=10,
            )
            return [f.strip() for f in result.stdout.split("\n") if f.strip()]
        except Exception as e:
            logger.warning("git_diff_failed", error=str(e))
            return []
