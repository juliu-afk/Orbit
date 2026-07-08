"""GEPA Prompt 进化引擎 (Phase G1).

对标: GEPA (ICLR 2026 Oral, Nous Research)——Genetic-Pareto Prompt Evolution
WHY: GEPA 比 GRPO 高 6% 准确率，用 35x 更少数据，不需要 GPU 训练。
     核心思路: 读执行轨迹→理解为什么失败→生成定向 Prompt 变异→遗传筛选。

设计:
  - 变异算子: 基于失败反思生成 Prompt 修改建议
  - 交叉算子: 合并两条高效用原则
  - Pareto 筛选: 准确率↑ + Token消耗↓ 双目标
  - 迭代: 每轮保留 top-K，生成变体，评估，筛选
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient
    from orbit.evolution.distill import DistillationEngine, StrategyPrinciple

import structlog

logger = structlog.get_logger("orbit.evolution.gepa")

# GEPA 变异 Prompt——基于失败反思生成改进
MUTATION_PROMPT = """You are optimizing an agent's strategy principle. The current principle performed poorly.

Current principle: {principle}
Failure reason: {failure_reason}
Success rate: {success_rate:.0%}

Generate 3 improved versions of this principle. Each should:
1. Be more specific about WHEN to apply it
2. Be more actionable about WHAT to do
3. Be concise (one sentence)

Output JSON array of 3 strings: ["improved v1", "improved v2", "improved v3"]"""

# GEPA 交叉 Prompt——合并两条高原则
CROSSOVER_PROMPT = """Merge these two successful principles into one stronger principle:

Principle A (utility {util_a:.0%}): {principle_a}
Principle B (utility {util_b:.0%}): {principle_b}

Output a single merged principle (one sentence) that combines the best of both.
JSON: {{"merged": "the combined principle"}}"""


class GEPAPopulation:
    """GEPA 种群——一组候选原则 + 遗传操作。"""

    def __init__(
        self, population_size: int = 10, elite_size: int = 3,
        conformal: object | None = None,  # V14.2+Theory 方向16: ConformalPredictor
    ) -> None:
        self.population_size = population_size
        self.elite_size = elite_size
        self._conformal = conformal

    def select_elite(self, principles: list[StrategyPrinciple]) -> list[StrategyPrinciple]:
        """选择精英——高效用 top-K。

        V14.2+Theory 方向16: 若共形预测器可用，用 p-value 替代硬阈值 utility>0.6。
        p > α(=0.05) → 原则可接受，保留。
        """
        # 共形筛选——p-value > 0.05 的原则保留
        # task=category(原则类别), code=principle(原则文本)——语义分离
        if self._conformal is not None:
            filtered = []
            for p in principles:
                p_val = self._conformal.p_value(p.category or "general", p.principle)
                if p_val > 0.05:
                    filtered.append(p)
            # 如果筛选后太少，至少保留 top-1
            if len(filtered) < 1 and principles:
                filtered = [max(principles, key=lambda p: p.utility_score)]
            ranked = sorted(filtered, key=lambda p: p.utility_score, reverse=True)
            return ranked[: self.elite_size]

        # 无共形预测器——退回到原始硬阈值
        ranked = sorted(principles, key=lambda p: p.utility_score, reverse=True)
        return ranked[: self.elite_size]

    def select_parents(self, principles: list[StrategyPrinciple]) -> tuple[StrategyPrinciple, StrategyPrinciple]:
        """选择两个不同父本——高效用加权随机。"""
        ranked = sorted(principles, key=lambda p: p.utility_score, reverse=True)[:6]
        if len(ranked) < 2:
            return ranked[0], ranked[0]
        weights = [p.utility_score + 0.1 for p in ranked]
        p1, p2 = random.choices(ranked, weights=weights, k=2)
        while p1 is p2 and len(ranked) > 1:
            p2 = random.choices(ranked, weights=weights, k=1)[0]
        return p1, p2


class GEPAEngine:
    """GEPA Prompt 进化引擎。

    用法:
        engine = GEPAEngine(llm=llm, distill=de)
        improved = await engine.evolve_population(
            principles=de.top_principles(20),
            failure_reason="原则太泛，Agent 不知道何时触发"
        )
    """

    GENERATIONS = 3  # 迭代代数

    def __init__(
        self, llm: LLMClient | None = None,
        distill: DistillationEngine | None = None,
        causal_analyzer: object | None = None,  # V14.2+Theory: RootCauseAnalyzer
        conformal: object | None = None,        # V14.2+Theory 方向16: ConformalPredictor
    ) -> None:
        self._llm = llm
        self._distill = distill
        self._causal = causal_analyzer
        self._population = GEPAPopulation(conformal=conformal)  # P0-5修复: 注入共形预测器

    async def evolve_population(
        self, principles: list[StrategyPrinciple],
        failure_reason: str = "", category: str = "",
    ) -> list[StrategyPrinciple]:
        """GEPA 主循环——遗传+筛选 N 代。

        Returns: 进化后的原则列表
        """
        if len(principles) < 3 or self._llm is None:
            return principles

        pop = principles[:]
        for gen in range(self.GENERATIONS):
            # 1. 选择精英——直接保留
            elite = self._population.select_elite(pop)
            next_gen = list(elite)

            # 2. 变异——基于失败反思
            for p in pop:
                if p.utility_score < 0.6 and random.random() < 0.5:
                    mutants = await self._mutate(p, failure_reason)
                    for m in mutants:
                        next_gen.append(m)

            # 3. 交叉——合并高效用原则
            for _ in range(3):
                pa, pb = self._population.select_parents(pop)
                if pa.id != pb.id:
                    child = await self._crossover(pa, pb)
                    if child:
                        next_gen.append(child)

            # 4. Pareto 筛选——去重 + 保留 top-K
            seen: set[str] = set()
            unique: list[StrategyPrinciple] = []
            for p in sorted(next_gen, key=lambda x: x.utility_score, reverse=True):
                key = p.principle[:60]
                if key not in seen:
                    seen.add(key)
                    unique.append(p)
            pop = unique[: self._population.population_size]

            logger.debug("gepa_generation", gen=gen, size=len(pop))

        return pop

    async def _mutate(
        self, principle: StrategyPrinciple, failure_reason: str,
    ) -> list[StrategyPrinciple]:
        """变异——LLM 生成 3 个改进版本。"""
        prompt = MUTATION_PROMPT.format(
            principle=principle.principle,
            failure_reason=failure_reason or "原则未有效提升任务成功率",
            success_rate=principle.utility_score,
        )
        try:
            from orbit.gateway.schemas import LLMRequest
            req = LLMRequest(prompt=prompt, system_prompt="Output JSON array only.", task_type="structured_output")
            result = await self._llm.generate(req, task_id="gepa_mutate")
            variants = json.loads(result.content.strip())
            if not isinstance(variants, list): variants = [str(variants)]
        except Exception:
            return []

        mutants: list[StrategyPrinciple] = []
        for v in variants[:3]:
            v = str(v).strip()
            if v and v != principle.principle and self._distill:
                p = self._distill._add_principle(
                    v, source="gepa_mutate", category=principle.category,
                    initial_score=principle.utility_score * 0.8,  # 变异初始分=原分*0.8
                )
                if p: mutants.append(p)
        return mutants

    async def _crossover(
        self, pa: StrategyPrinciple, pb: StrategyPrinciple,
    ) -> StrategyPrinciple | None:
        """交叉——LLM 合并两条高效用原则。"""
        prompt = CROSSOVER_PROMPT.format(
            util_a=pa.utility_score, principle_a=pa.principle,
            util_b=pb.utility_score, principle_b=pb.principle,
        )
        try:
            from orbit.gateway.schemas import LLMRequest
            req = LLMRequest(prompt=prompt, system_prompt="Output JSON only.", task_type="structured_output")
            result = await self._llm.generate(req, task_id="gepa_crossover")
            data = json.loads(result.content.strip())
            merged = data.get("merged", "")
        except Exception:
            return None

        if merged and self._distill:
            avg_score = (pa.utility_score + pb.utility_score) / 2
            return self._distill._add_principle(
                merged, source="gepa_crossover",
                category=pa.category or pb.category, initial_score=avg_score,
            )
        return None
