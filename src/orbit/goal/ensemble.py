"""ModelEnsemble——多模型并行集成。

对标 ICML 2025 LLMSelector + Simula 多样性集成研究:
- 多样性优先: 不同模型族并行（非同模型多次采样）
- 独立 judge 三维评分: 正确性/性能/可维护性
- 成本控制: 仅子任务权重 > 阈值时启用

策略:
- 权重 > 1.0? → 启用集成（2-3 模型并行）
- 各模型独立执行 → judge 评分 → 选最优
- 前两名分差 <5%? → 触发融合（取各方案最佳部分）
"""

from __future__ import annotations

import structlog
from typing import Any

logger = structlog.get_logger("orbit.goal")

# 集成触发阈值——子任务权重 > 此值才启用
ENSEMBLE_WEIGHT_THRESHOLD = 1.0
# 融合触发阈值——前两名分差 < 此值触发融合
FUSION_DELTA_THRESHOLD = 0.05
# 最大候选模型数
MAX_ENSEMBLE_CANDIDATES = 3


class JudgeScore:
    """Judge 评分。"""

    def __init__(
        self,
        correctness: float = 0.0,
        performance: float = 0.0,
        maintainability: float = 0.0,
    ) -> None:
        self.correctness = correctness
        self.performance = performance
        self.maintainability = maintainability

    @property
    def total(self) -> float:
        """加权总分——正确性 50% + 性能 25% + 可维护性 25%。"""
        return self.correctness * 0.50 + self.performance * 0.25 + self.maintainability * 0.25


class EnsembleResult:
    """集成执行结果。"""

    def __init__(
        self,
        selected: Any = None,  # 选中的最佳方案
        candidates: list[Any] | None = None,
        scores: list[JudgeScore] | None = None,
        method: str = "selection",  # selection | fusion | single
    ) -> None:
        self.selected = selected
        self.candidates = candidates or []
        self.scores = scores or []
        self.method = method

    @property
    def is_fused(self) -> bool:
        return self.method == "fusion"


class ModelEnsemble:
    """多模型并行集成。

    Usage:
        ensemble = ModelEnsemble(
            agent_factory=factory,
            judge_llm=judge_client,
            ensemble_models=["claude-opus", "gpt-4o"],
        )
        result = await ensemble.execute(task, context, weight=1.5)
    """

    def __init__(
        self,
        agent_factory: Any = None,  # AgentFactory
        judge_llm: Any = None,  # LLMClient (judge)
        ensemble_models: list[str] | None = None,
        weight_threshold: float = ENSEMBLE_WEIGHT_THRESHOLD,
    ) -> None:
        self._agent_factory = agent_factory
        self._judge = judge_llm
        self._models = ensemble_models or []
        self._threshold = weight_threshold

    async def execute(
        self,
        task: Any,  # Task
        context: dict[str, Any],
        weight: float = 1.0,
        budget_per_model: int = 0,
    ) -> EnsembleResult:
        """执行——可能在单模型或多模型间选择。

        权重 <= 阈值 → 单模型（成本控制）
        权重 > 阈值 + models >= 2 → 多模型集成
        """
        if weight <= self._threshold or len(self._models) < 2:
            # 单模型
            result = await self._run_single(
                task, context, self._models[0] if self._models else None
            )
            return EnsembleResult(selected=result, method="single", candidates=[result])

        # 多模型并行
        candidates = []
        for model in self._models[:MAX_ENSEMBLE_CANDIDATES]:
            try:
                result = await self._run_single(task, context, model)
                candidates.append({"model": model, "output": result})
            except Exception as e:
                logger.warning("ensemble_candidate_failed", model=model, error=str(e))

        if len(candidates) < 2:
            return EnsembleResult(
                selected=candidates[0]["output"] if candidates else None,
                method="single",
            )

        # Judge 评分
        scores = await self._judge_candidates(task, candidates)

        # 选最优
        best_idx = max(range(len(scores)), key=lambda i: scores[i].total)

        # 前两名分差 < 阈值 → 融合
        method = "selection"
        if len(scores) >= 2:
            sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i].total, reverse=True)
            if (
                scores[sorted_indices[0]].total - scores[sorted_indices[1]].total
                < FUSION_DELTA_THRESHOLD
            ):
                method = "fusion"
                candidate = self._fuse(candidates, scores)
            else:
                candidate = candidates[best_idx]["output"]
        else:
            candidate = candidates[best_idx]["output"]

        logger.info(
            "ensemble_complete",
            task_id=getattr(task, "id", "?"),
            candidates=len(candidates),
            method=method,
            best_score=round(scores[best_idx].total, 3),
        )
        return EnsembleResult(
            selected=candidate, candidates=candidates, scores=scores, method=method
        )

    # ── 内部 ──────────────────────────────────────────

    async def _run_single(self, task: Any, context: dict, model: str | None) -> Any:
        """单模型执行——通过 AgentFactory。"""
        if not self._agent_factory:
            return f"[mock] 完成 {task.description[:100]}"
        agent = self._agent_factory.create("developer")
        from orbit.agents.base import AgentInput

        output = await agent.execute(
            AgentInput(
                task=getattr(task, "description", str(task)),
                context=context,
                role="developer",
            )
        )
        return output.result if output.status == "ok" else str(output.error)

    async def _judge_candidates(self, task: Any, candidates: list[dict]) -> list[JudgeScore]:
        """Judge 评分——三维度评估。"""
        if not self._judge:
            # 无 Judge → 选第一个（默认最新）
            scores = [JudgeScore(0.7, 0.7, 0.7) for _ in candidates]
            scores[0] = JudgeScore(0.8, 0.8, 0.8)
            return scores

        # TODO: LLM judge——三维度评分
        # 暂时回退到启发式评分
        scores = []
        for c in candidates:
            output_len = len(str(c.get("output", "")))
            scores.append(
                JudgeScore(
                    correctness=0.7 + min(output_len / 10000, 0.2),
                    performance=0.7,
                    maintainability=0.7,
                )
            )
        return scores

    def _fuse(self, candidates: list[dict], scores: list[JudgeScore]) -> Any:
        """融合多个候选方案的最佳部分。"""
        # TODO: 真正的融合逻辑——取各方案中得分最高的部分
        best_idx = max(range(len(scores)), key=lambda i: scores[i].total)
        return candidates[best_idx]["output"]
