"""测试-审查-进化三角闭环 —— Orbit 自循环系统的最外层闭环。

L4 (P3): 测试发现 → 审查确认 → 失败模式提取 → evolution/ Prompt 进化
→ 下次代码生成质量更高 → 测试更容易通过 → 审查发现更少 → 循环收敛。

对标: Orbit 研究报告 §8.4 L4 + Google MuRS 反馈闭环 + GEM 变异反馈。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("orbit.testing.triangle")


@dataclass
class FailurePattern:
    """一条经过测试+审查双重确认的失败模式。"""

    pattern_id: str = ""
    module: str = ""
    error_type: str = ""  # "test_failure" | "review_rejection" | "coverage_gap" | "ponytail_warning"
    description: str = ""
    frequency: int = 1  # 出现次数
    test_evidence: str = ""   # 测试侧的发现
    review_evidence: str = ""  # 审查侧的确认
    prompt_adjustment: str = ""  # 建议的 Prompt 调整方向
    last_seen: str = ""


@dataclass
class TriangleReport:
    """三角闭环的一次迭代报告。"""

    iteration: int = 0
    patterns_extracted: int = 0
    patterns_confirmed: int = 0  # 测试+审查双确认的
    prompt_changes: list[str] = field(default_factory=list)
    quality_delta: float = 0.0  # 本次闭环后的质量变化（正=改善）


class TriangleConnector:
    """三角闭环连接器——测试+审查发现 → evolution/ 进化信号。

    Usage:
        connector = TriangleConnector(evolution_engine, knowledge_store)
        report = await connector.close_loop(cross_report, module_name)
        # report.prompt_changes → evolution/ 在下一次同类任务中注入
    """

    # 失败模式在 knowledge/ 中的去重阈值——同模式出现 N 次才触发 Prompt 调整
    PATTERN_FREQUENCY_THRESHOLD: int = 2

    def __init__(self, evolution=None, knowledge=None):
        self._evolution = evolution  # EvolutionEngine (GEPA Prompt 进化)
        self._knowledge = knowledge  # MemoryStore / KnowledgeStore

    async def close_loop(
        self,
        cross_report: dict,
        module_name: str = "",
    ) -> TriangleReport:
        """执行一次三角闭环迭代。

        输入: CrossReport（测试结果 + 审查发现 + 分歧点）
        输出: TriangleReport（提取的失败模式 + Prompt 调整建议）

        闭环逻辑:
        1. 测试发现 failures → 审查确认 → 模式入库 knowledge/
        2. 同模式 frequency ≥2 → 触发 evolution/ Prompt 调整
        3. 下次同类任务 → 调整后的 Prompt → 质量提升 → 循环收敛
        """
        import uuid
        from datetime import datetime, timezone

        report = TriangleReport(iteration=0)
        now = datetime.now(timezone.utc).isoformat()

        # ── 1. 提取测试侧失败模式 ──
        test_result = cross_report.get("test_result", {})
        test_errors = getattr(test_result, "errors", []) if hasattr(test_result, "errors") else []

        # ── 2. 提取审查侧确认的发现 ──
        review_result = cross_report.get("review_result", {}) or {}
        review_issues = review_result.get("issues", [])
        divergent_points = cross_report.get("divergent_points", [])

        # ── 3. 交叉确认: 测试失败 + 审查拒绝/警告 → 确定模式 ──
        patterns: list[FailurePattern] = []

        # 3a. 测试失败 → 审查是否也发现问题？
        for error in test_errors[:5]:  # 最多 5 条
            error_str = str(error)[:200]
            # 检查审查是否在同一文件/模块有发现
            review_confirmed = any(
                issue.get("file", "") in module_name or module_name in issue.get("file", "")
                for issue in review_issues
            )
            if review_confirmed:
                patterns.append(FailurePattern(
                    pattern_id=uuid.uuid4().hex[:12],
                    module=module_name,
                    error_type="test_failure",
                    description=error_str,
                    test_evidence=error_str,
                    review_evidence="审查确认——同模块存在问题",
                    prompt_adjustment=f"在 {module_name} 模块的 Prompt 中强调: {error_str}",
                    last_seen=now,
                ))

        # 3b. 分歧点——测试通过但审查拒绝 → 审查维度缺失（命名/架构/过度工程）
        for dp in divergent_points[:3]:
            patterns.append(FailurePattern(
                pattern_id=uuid.uuid4().hex[:12],
                module=module_name,
                error_type="review_rejection",
                description=f"分歧: {dp.get('target', '')} — {dp.get('review_reason', '')}",
                test_evidence=f"测试: {dp.get('test_verdict', 'PASSED')}",
                review_evidence=f"审查: {dp.get('review_verdict', 'WARNING')} — {dp.get('review_reason', '')}",
                prompt_adjustment=dp.get("suggestion", "审查发现需在 Prompt 中约束"),
                last_seen=now,
            ))

        # 3c. Ponytail 过度工程发现
        ponytail_count = review_result.get("ponytail_count", 0)
        if ponytail_count > 0:
            ponytail_issues = [
                i for i in review_issues if i.get("source") == "ponytail"
            ]
            if ponytail_issues:
                patterns.append(FailurePattern(
                    pattern_id=uuid.uuid4().hex[:12],
                    module=module_name,
                    error_type="ponytail_warning",
                    description=f"过度工程检测: {ponytail_count} 个发现",
                    test_evidence="N/A（静态检测，非运行时）",
                    review_evidence=f"{ponytail_count} 个 Ponytail 发现",
                    prompt_adjustment="Prompt 中加入 '避免过度抽象，优先简单方案'",
                    last_seen=now,
                ))

        report.patterns_extracted = len(patterns)

        # ── 4. 持久化到 knowledge/ + 去重 ──
        confirmed_patterns: list[FailurePattern] = []
        for pattern in patterns:
            frequency = await self._upsert_pattern(pattern)
            pattern.frequency = frequency
            if frequency >= self.PATTERN_FREQUENCY_THRESHOLD:
                confirmed_patterns.append(pattern)

        report.patterns_confirmed = len(confirmed_patterns)

        # ── 5. 触发 evolution/ Prompt 进化 ──
        for pattern in confirmed_patterns:
            if self._evolution:
                try:
                    # 将确认的失败模式注入 GEPA Prompt 进化
                    signal = {
                        "source": "triangle",
                        "module": module_name,
                        "pattern": pattern.description,
                        "adjustment": pattern.prompt_adjustment,
                        "frequency": pattern.frequency,
                        "timestamp": now,
                    }
                    await self._evolution.inject_signal(signal)
                    report.prompt_changes.append(pattern.prompt_adjustment)
                    logger.info(
                        "triangle_prompt_evolved",
                        module=module_name,
                        pattern=pattern.description[:100],
                        frequency=pattern.frequency,
                    )
                except Exception as e:
                    logger.warning("triangle_evolution_inject_failed", error=str(e))

        report.iteration = 1 if confirmed_patterns else 0
        logger.info(
            "triangle_closed_loop",
            module=module_name,
            patterns=report.patterns_extracted,
            confirmed=report.patterns_confirmed,
            prompt_changes=len(report.prompt_changes),
        )
        return report

    async def _upsert_pattern(self, pattern: FailurePattern) -> int:
        """将失败模式持久化到 knowledge/ ，返回出现频次。"""
        if not self._knowledge:
            return 1

        try:
            # 检查 knowledge/ 是否已有相似模式
            from orbit.memory.models import MemorySearchQuery

            results = self._knowledge.search(MemorySearchQuery(
                query=pattern.description,
                max_results=3,
            ))
            for r in (results or []):
                snippet = getattr(r, "snippet", "") if hasattr(r, "snippet") else str(r)
                if pattern.error_type in snippet and pattern.module in snippet:
                    # 已存在——增加频率
                    pattern.frequency = getattr(r, "frequency", 1) + 1
                    await self._knowledge.update_frequency(
                        pattern_id=pattern.pattern_id,
                        frequency=pattern.frequency,
                    )
                    return pattern.frequency

            # 新模式——存入
            await self._knowledge.store_failure_pattern({
                "type": "failure_pattern",
                "module": pattern.module,
                "error_type": pattern.error_type,
                "description": pattern.description,
                "frequency": 1,
                "prompt_adjustment": pattern.prompt_adjustment,
                "last_seen": pattern.last_seen,
            })
            return 1
        except Exception as e:
            logger.debug("triangle_pattern_upsert_failed", error=str(e))
            return 1  # fail-open——不阻塞主流程
