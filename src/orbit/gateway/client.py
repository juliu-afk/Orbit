"""LLMClient（Step 2.1）：统一 LLM 网关。

WHY 统一网关：调度器只认 LLMClient.generate()，不直接接触 litellm。
好处：① 密钥/路由/成本追踪集中管理；② 熔断器透明；③ 切模型不改调度器。

主备降级（PRD SC5）：主力连续失败 2 次 → 自动切备选模型。
熔断（PRD SC2/SC3）：单模型连续 5 次失败 → 熔断 60s → 半开探测。
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.gateway.circuit_breaker import CircuitBreaker, CircuitOpenError
from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage

logger = structlog.get_logger()

# 模型定价（USD / 1K tokens）。来源：DeepSeek/Qwen 官方定价。
# WHY 集中定价：成本追踪的基础，调价只改这里。
PRICES: dict[str, dict[str, float]] = {
    "deepseek/deepseek-chat": {
        "prompt": 0.001,  # DeepSeek 输入约 $0.001/1K（缓存命中更便宜）
        "completion": 0.002,
    },
    "qwen/qwen-plus": {
        "prompt": 0.002,
        "completion": 0.006,
    },
}

DEFAULT_MODEL = "deepseek/deepseek-chat"
FALLBACK_MODEL = "qwen/qwen-plus"
# 主力连续失败次数达到此阈值则切备选（PRD SC5：2 次失败切换）
FALLBACK_FAILURE_THRESHOLD = 2


class LLMClient:
    """统一 LLM 调用入口。

    被调度器调用（src/orbit/scheduler/）。
    内部依赖 CircuitBreaker（按模型粒度）+ litellm.acompletion。
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker | None = None,
        default_model: str = DEFAULT_MODEL,
        fallback_model: str = FALLBACK_MODEL,
    ):
        self.cb = circuit_breaker or CircuitBreaker()
        self.default_model = default_model
        self.fallback_model = fallback_model
        # 调用记录（task_id -> [usage]）供 get_usage_stats
        self._usage_log: dict[str, list[LLMUsage]] = {}

    async def generate(self, req: LLMRequest, task_id: str) -> LLMResponse:
        """调用 LLM，自动主备降级 + 熔断保护。

        Raises:
            CircuitOpenError: 主备模型均熔断时抛出（调用方应快速失败）。
        """
        # 主力模型尝试
        try:
            return await self._call_with_circuit(self.default_model, req, task_id)
        except CircuitOpenError:
            # 主力熔断 → 尝试备选
            logger.warning("primary_circuit_open_fallback", model=self.default_model)
            return await self._call_with_circuit(self.fallback_model, req, task_id)
        except Exception as e:
            # 主力失败但未熔断 → 记录后试备选
            logger.warning(
                "primary_failed_trying_fallback",
                model=self.default_model,
                error=str(e),
            )
            return await self._call_with_circuit(self.fallback_model, req, task_id)

    async def _call_with_circuit(self, model: str, req: LLMRequest, task_id: str) -> LLMResponse:
        """单模型调用 + 熔断器保护。"""
        await self.cb.before_call(model)
        try:
            resp = await self._do_completion(model, req)
            await self.cb.record_success(model)
            self._log_usage(task_id, resp.usage)
            logger.info(
                "llm_call_ok",
                model=model,
                task_id=task_id,
                tokens=resp.usage.total_tokens,
                cost=resp.usage.cost_usd,
            )
            return resp
        except Exception as e:
            await self.cb.record_failure(model)
            logger.warning(
                "llm_call_failed",
                model=model,
                task_id=task_id,
                error=str(e),
            )
            raise

    async def _do_completion(self, model: str, req: LLMRequest) -> LLMResponse:
        """调用 litellm.acompletion（真实 LLM）。

        WHY 用 acompletion 异步：与调度器异步模型一致（ADR 技术约束）。
        Mock 时由测试 patch 此方法。
        """
        # 延迟导入 litellm，避免未装包时 import 失败影响测试
        try:
            import litellm  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "litellm 未安装。生产环境需 poetry install，测试请 mock _do_completion"
            ) from e

        result = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.prompt},
            ],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        content = result.choices[0].message.content or ""
        usage_raw = result.usage
        usage = self._build_usage(model, usage_raw)
        return LLMResponse(content=content, model=model, usage=usage)

    def _build_usage(self, model: str, usage_raw: Any) -> LLMUsage:
        """从 litellm usage 对象构造 LLMUsage（含成本计算）。"""
        prompt_t = getattr(usage_raw, "prompt_tokens", 0) or 0
        completion_t = getattr(usage_raw, "completion_tokens", 0) or 0
        total_t = getattr(usage_raw, "total_tokens", prompt_t + completion_t) or (
            prompt_t + completion_t
        )
        price = PRICES.get(model, {"prompt": 0.0, "completion": 0.0})
        cost = (prompt_t / 1000.0 * price["prompt"]) + (completion_t / 1000.0 * price["completion"])
        return LLMUsage(
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
            cost_usd=round(cost, 6),
        )

    def _log_usage(self, task_id: str, usage: LLMUsage) -> None:
        self._usage_log.setdefault(task_id, []).append(usage)

    def get_usage_stats(self, task_id: str) -> LLMUsage:
        """查询任务累计 Token 消耗与成本（PRD 需求⑥）。"""
        records = self._usage_log.get(task_id, [])
        if not records:
            return LLMUsage()
        return LLMUsage(
            prompt_tokens=sum(r.prompt_tokens for r in records),
            completion_tokens=sum(r.completion_tokens for r in records),
            total_tokens=sum(r.total_tokens for r in records),
            cost_usd=round(sum(r.cost_usd for r in records), 6),
        )
