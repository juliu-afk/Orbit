"""LLMClient（Step 2.1）：统一 LLM 网关。

WHY 统一网关：调度器只认 LLMClient.generate()，不直接接触 litellm。
好处：密钥/路由/成本追踪集中管理；熔断器透明；切模型不改调度器。

模型体系（2026-06-26 修订）：
- DeepSeek V4 Pro  → 主力推理（architect/developer）
- DeepSeek V4 Flash → 轻量任务（config_manager/clarifier）
- GLM-5.2          → 代码审查+测试设计（reviewer/qa），走 Coding Plan 订阅
- GLM-4.7 Flash    → 统一降级兜底（免费），走 Coding Plan 订阅

降级策略：主力失败 → 自动切 GLM-4.7 Flash（免费）→ 失败挂起人工。
熔断（PRD SC2/SC3）：单模型连续 5 次失败 → 熔断 60s → 半开探测。
"""

from __future__ import annotations
from typing import Any
import structlog
from orbit.core.config import settings
from orbit.gateway.circuit_breaker import CircuitBreaker, CircuitOpenError
from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage

logger = structlog.get_logger()

PRICES: dict[str, dict[str, float]] = {
    "deepseek/deepseek-v4-pro": {"prompt": 0.000435, "completion": 0.00087},
    "deepseek/deepseek-v4-flash": {"prompt": 0.00014, "completion": 0.00028},
    "openai/glm-5.2": {"prompt": 0.0, "completion": 0.0},
    "openai/glm-4.7-flash": {"prompt": 0.0, "completion": 0.0},
}

MODEL_PRO = "deepseek/deepseek-v4-pro"
MODEL_FLASH = "deepseek/deepseek-v4-flash"
MODEL_GLM5 = "openai/glm-5.2"
MODEL_GLM_FALLBACK = "openai/glm-4.7-flash"
GLM_API_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"


class LLMClient:
    def __init__(
        self, circuit_breaker=None, default_model=MODEL_PRO, fallback_model=MODEL_GLM_FALLBACK
    ):
        self.cb = circuit_breaker or CircuitBreaker()
        self.default_model = default_model
        self.fallback_model = fallback_model
        self._usage_log: dict[str, list[LLMUsage]] = {}

    async def generate(self, req: LLMRequest, task_id: str) -> LLMResponse:
        try:
            return await self._call_with_circuit(self.default_model, req, task_id)
        except CircuitOpenError:
            logger.warning("primary_circuit_open", model=self.default_model)
        except Exception as e:
            logger.warning("primary_failed", model=self.default_model, error=str(e))
        try:
            logger.info("fallback_to_glm47flash", original=self.default_model)
            return await self._call_with_circuit(self.fallback_model, req, task_id)
        except CircuitOpenError:
            logger.error("fallback_circuit_open", model=self.fallback_model)
            raise
        except Exception as e:
            logger.error("fallback_failed", model=self.fallback_model, error=str(e))
            raise

    async def _call_with_circuit(self, model: str, req: LLMRequest, task_id: str) -> LLMResponse:
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
            logger.warning("llm_call_failed", model=model, task_id=task_id, error=str(e))
            raise

    async def _do_completion(self, model: str, req: LLMRequest) -> LLMResponse:
        try:
            import litellm  # noqa: F401
        except ImportError as e:
            raise RuntimeError("litellm 未安装") from e
        if model.startswith("openai/glm"):
            result = await litellm.acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": req.system_prompt},
                    {"role": "user", "content": req.prompt},
                ],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                api_base=GLM_API_BASE,
                api_key=settings.ZAI_API_KEY,
            )
        else:
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
        usage = self._build_usage(model, result.usage)
        return LLMResponse(content=content, model=model, usage=usage)

    async def generate_stream(self, req, task_id, entropy_monitor=None):
        import litellm
        from orbit.hallucination.schemas import HighEntropyError

        model = self.default_model
        try:
            stream = await self._stream_completion(model, req, entropy_monitor)
        except Exception as e:
            logger.warning("stream_primary_failed", model=model, error=str(e))
            model = self.fallback_model
            stream = await self._stream_completion(model, req, entropy_monitor)
        content_parts = []
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            token_text = delta.content or ""
            if token_text:
                content_parts.append(token_text)
            if entropy_monitor and hasattr(delta, "logprobs") and delta.logprobs:
                for lp in (delta.logprobs.content if delta.logprobs.content else []):
                    logprob_list = (
                        [t.logprob for t in lp.top_logprobs]
                        if hasattr(lp, "top_logprobs") and lp.top_logprobs
                        else [lp.logprob]
                    )
                    entropy = entropy_monitor.on_token(lp.token, logprob_list)
                    if entropy is not None:
                        raise HighEntropyError(
                            entropy=entropy, threshold=entropy_monitor.config.threshold
                        )
        content = "".join(content_parts)
        return LLMResponse(content=content, model=model, usage=LLMUsage())  # type: ignore[call-arg]

    async def _stream_completion(self, model, req, entropy_monitor=None):
        import litellm

        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.prompt},
            ],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
        )
        if model.startswith("openai/glm"):
            kwargs["api_base"] = GLM_API_BASE
            kwargs["api_key"] = settings.ZAI_API_KEY
        if entropy_monitor:
            kwargs["logprobs"] = True
        return await litellm.acompletion(**kwargs)

    def _build_usage(self, model, usage_raw):
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

    def _log_usage(self, task_id, usage):
        self._usage_log.setdefault(task_id, []).append(usage)

    def get_usage_stats(self, task_id):
        records = self._usage_log.get(task_id, [])
        if not records:
            return LLMUsage()  # type: ignore[call-arg]
        return LLMUsage(
            prompt_tokens=sum(r.prompt_tokens for r in records),
            completion_tokens=sum(r.completion_tokens for r in records),
            total_tokens=sum(r.total_tokens for r in records),
            cost_usd=round(sum(r.cost_usd for r in records), 6),
        )
