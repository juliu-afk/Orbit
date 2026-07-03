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

from typing import Any

import structlog

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
                candidate = await self._fuse(candidates, scores)
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
        """Judge 评分——三维度评估（正确性/性能/可维护性）。

        有 judge_llm 时通过 LLM 结构化评分；否则启发式回退（输出长度加权）。
        """
        if not self._judge:
            # 无 Judge → 选第一个（默认最新）
            scores = [JudgeScore(0.7, 0.7, 0.7) for _ in candidates]
            scores[0] = JudgeScore(0.8, 0.8, 0.8)
            return scores

        # LLM judge——三维度结构化评分
        scores = []
        for i, c in enumerate(candidates):
            try:
                prompt = self._build_judge_prompt(task, c, i)
                response = await self._judge.complete(prompt)
                parsed = self._parse_judge_response(response)
                scores.append(
                    JudgeScore(
                        correctness=parsed.get("correctness", 0.7),
                        performance=parsed.get("performance", 0.7),
                        maintainability=parsed.get("maintainability", 0.7),
                    )
                )
            except Exception as e:
                logger.warning("judge_scoring_failed", candidate=i, error=str(e))
                # 评分失败→退回到启发式，标记偏低
                output_len = len(str(c.get("output", "")))
                scores.append(
                    JudgeScore(
                        correctness=0.5 + min(output_len / 15000, 0.3),
                        performance=0.5,
                        maintainability=0.5,
                    )
                )
        return scores

    @staticmethod
    def _build_judge_prompt(task: Any, candidate: dict, idx: int) -> str:
        """构建 judge 评分 prompt。"""
        task_desc = getattr(task, "description", str(task))[:500]
        output = str(candidate.get("output", ""))[:3000]
        return (
            f"你是一位资深代码审查专家。请对以下任务输出进行三维度评分（0.0-1.0）。\n\n"
            f"## 任务\n{task_desc}\n\n"
            f"## 候选方案 #{idx + 1} 输出\n```\n{output}\n```\n\n"
            f"请以 JSON 格式返回评分：\n"
            f'{{"correctness": 0.85, "performance": 0.72, "maintainability": 0.80, "reason": "简要理由"}}\n'
            f"评分标准：\n"
            f"- correctness: 逻辑是否正确、边界情况是否处理\n"
            f"- performance: 时间复杂度、I/O 效率、缓存利用\n"
            f"- maintainability: 命名规范、注释质量、模块化程度"
        )

    @staticmethod
    def _parse_judge_response(response: str) -> dict[str, float]:
        """解析 judge 返回的 JSON——容错处理。"""
        import json as _json

        try:
            data = _json.loads(response)
            return {k: float(v) for k, v in data.items() if k in ("correctness", "performance", "maintainability")}
        except (_json.JSONDecodeError, ValueError, TypeError):
            pass
        # 尝试从文本中提取分数
        import re

        result = {}
        for key in ("correctness", "performance", "maintainability"):
            m = re.search(rf'"{key}"\s*:\s*([0-9.]+)', response)
            if m:
                try:
                    result[key] = float(m.group(1))
                except ValueError:
                    pass
        return result if result else {"correctness": 0.7, "performance": 0.7, "maintainability": 0.7}

    async def _fuse(self, candidates: list[dict], scores: list[JudgeScore]) -> Any:
        """融合多个候选方案的最佳部分。

        WHY 融合而非单选: 前两名分差 < 5% 时，两方案各有优势——
        融合取其长处，产出优于任一单独方案。
        有 judge_llm 时通过 LLM 对比融合；否则选最佳方案。
        """
        # 确定融合的候选（前 2 名）
        sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i].total, reverse=True)
        top_indices = sorted_indices[:2]
        if len(top_indices) < 2:
            return candidates[sorted_indices[0]]["output"]

        if self._judge:
            try:
                # 从候选输出中提取任务上下文（取首个非空摘要）
                task_desc = "未知任务"
                for c in candidates[:2]:
                    out = str(c.get("output", ""))[:80]
                    if out.strip():
                        task_desc = out
                        break
                prompt = self._build_fusion_prompt(
                    task_desc,
                    candidates[top_indices[0]]["output"],
                    candidates[top_indices[1]]["output"],
                    scores[top_indices[0]],
                    scores[top_indices[1]],
                )
                fused = await self._judge.complete(prompt)
                if fused and len(str(fused)) > 10:
                    logger.info("fusion_success", method="llm")
                    return fused
            except Exception as e:
                logger.warning("fusion_failed_fallback_to_best", error=str(e))

        # 回退：选总分最高的方案
        logger.info("fusion_fallback_best", method="best")
        return candidates[top_indices[0]]["output"]

    @staticmethod
    def _build_fusion_prompt(
        task_desc: str,
        output_a: str,
        output_b: str,
        score_a: JudgeScore,
        score_b: JudgeScore,
    ) -> str:
        """构建融合 prompt——取两方案最佳部分合并。"""
        return (
            f"你是一位资深软件工程师。请将以下两个方案融合为一个最优方案，"
            f"保留每个方案的最佳部分。\n\n"
            f"## 任务\n{task_desc[:500]}\n\n"
            f"## 方案 A（正确性={score_a.correctness:.2f} 性能={score_a.performance:.2f} 可维护性={score_a.maintainability:.2f}）\n"
            f"```\n{str(output_a)[:3000]}\n```\n\n"
            f"## 方案 B（正确性={score_b.correctness:.2f} 性能={score_b.performance:.2f} 可维护性={score_b.maintainability:.2f}）\n"
            f"```\n{str(output_b)[:3000]}\n```\n\n"
            f"## 融合要求\n"
            f"1. 方案 A 的强项保留，方案 B 的强项保留\n"
            f"2. 不重复或矛盾\n"
            f"3. 输出完整的融合方案代码/文档\n"
            f"直接输出融合结果，无需解释过程。"
        )
