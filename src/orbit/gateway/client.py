"""LLMClient（Step 2.1）：统一 LLM 网关。

WHY 统一网关：调度器只认 LLMClient.generate()，不直接接触 litellm。
好处：密钥/路由/成本追踪集中管理；熔断器透明；切模型不改调度器。

模型体系（2026-06-26 修订，Tier 换位）：
- GLM-5.2          → Tier 3 最强推理（architect），走 Coding Plan 订阅
- DeepSeek V4 Pro  → Tier 2 中档推理（developer/reviewer/qa）
- DeepSeek V4 Flash → Tier 1 轻量任务（config_manager/clarifier）
- GLM-4.7 Flash    → 统一降级兜底（免费），走 Coding Plan 订阅

降级策略：主力失败 → 自动切 GLM-4.7 Flash（免费）→ 失败挂起人工。
熔断（PRD SC2/SC3）：单模型连续 5 次失败 → 熔断 60s → 半开探测。
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.core.config import settings
from orbit.gateway.adapters import ProviderAdapter
from orbit.gateway.adapters.anthropic import AnthropicAdapter
from orbit.gateway.adapters.openai import OpenAIAdapter
from orbit.gateway.circuit_breaker import CircuitBreaker, CircuitOpenError
from orbit.gateway.routing import RoutingStrategy, select_model
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
        self,
        circuit_breaker=None,
        default_model=MODEL_PRO,
        fallback_model=MODEL_GLM_FALLBACK,
        resolver=None,  # AgentModelResolver（Step 2.3）
    ):
        self.cb = circuit_breaker or CircuitBreaker()
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.resolver = resolver  # Step 2.3: 智能路由
        self._usage_log: dict[str, list[LLMUsage]] = {}
        # Phase 3: provider adapter 缓存（按 provider name）
        self._adapters: dict[str, ProviderAdapter] = {
            "anthropic": AnthropicAdapter(),
            "openai": OpenAIAdapter(),
        }

    def _get_adapter(self, model: str, provider: str | None = None) -> ProviderAdapter:
        """按 model 或显式 provider 获取适配器。

        WHY 缓存: adapter 是无状态的纯函数，不需要每次 new。
        """
        if provider:
            return self._adapters.get(provider, OpenAIAdapter())
        # 自动检测
        if model.startswith("openai/") or model.startswith("deepseek/"):
            return self._adapters["openai"]
        if model.startswith("anthropic/"):
            return self._adapters["anthropic"]
        return OpenAIAdapter()  # 默认——大多数 provider 兼容 OpenAI format

    async def generate(
        self,
        req: LLMRequest,
        task_id: str,
        agent_name: str = "",  # Step 2.3: Agent 名称
        router_decision=None,  # Step 2.3: RouterDecision
        routing_strategy: RoutingStrategy | None = None,  # Phase 3: 路由策略
    ) -> LLMResponse:
        # Step 2.3: 通过 Resolver 获取实际模型（而非硬编码 default_model）
        model = self.default_model
        model_source = "default"

        # Phase 3: RoutingStrategy 优先于 agent Resolver
        if routing_strategy is not None and routing_strategy != RoutingStrategy.AGENT_DEFAULT:
            decision = select_model(routing_strategy)
            # cheapest 策略避免选非免费模型
            model = decision.model
            model_source = f"routing_{routing_strategy.value}"
            logger.info(
                "routing_strategy_applied",
                strategy=routing_strategy.value,
                model=model,
                reason=decision.reason,
            )

        elif self.resolver and agent_name:
            try:
                from orbit.router.resolver import AgentModelResolver

                if isinstance(self.resolver, AgentModelResolver):
                    resolved = await self.resolver.resolve(agent_name, router_decision)
                    model = resolved.model or self.default_model
                    model_source = resolved.source
                    logger.info(
                        "router_model_selected",
                        agent=agent_name,
                        model=model,
                        source=model_source,
                    )
            except Exception as e:
                logger.warning("router_resolve_failed", error=str(e))

        try:
            return await self._call_with_circuit(model, req, task_id, model_source)
        except CircuitOpenError:
            logger.warning("primary_circuit_open", model=model)
        except Exception as e:
            logger.warning("primary_failed", model=model, error=str(e))
        try:
            logger.info("fallback_to_glm47flash", original=model)
            return await self._call_with_circuit(self.fallback_model, req, task_id, "fallback")
        except CircuitOpenError:
            logger.error("fallback_circuit_open", model=self.fallback_model)
            raise
        except Exception as e:
            logger.error("fallback_failed", model=self.fallback_model, error=str(e))
            raise

    async def _call_with_circuit(
        self, model: str, req: LLMRequest, task_id: str, model_source: str = "default"
    ) -> LLMResponse:
        await self.cb.before_call(model)
        try:
            resp = await self._do_completion(model, req)
            await self.cb.record_success(model)
            resp.model_source = model_source  # Step 2.3: 记录模型来源供审计
            self._log_usage(task_id, resp.usage)
            logger.info(
                "llm_call_ok",
                model=model,
                task_id=task_id,
                source=model_source,
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

        # Phase 1: 支持多轮消息历史（ReAct 循环）
        if req.messages:
            messages = req.messages
        else:
            messages = [
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.prompt},
            ]

        # Phase 3: 通过 adapter 标准化消息和工具 schema
        adapter = self._get_adapter(model, req.provider)
        messages = adapter.normalize_messages(messages)
        tools_schema = adapter.normalize_tool_schema(req.tools) if req.tools else None

        # 构建 litellm 参数
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

        # GLM 模型特殊配置
        if model.startswith("openai/glm"):
            kwargs["api_base"] = GLM_API_BASE
            kwargs["api_key"] = settings.ZAI_API_KEY

        # Phase 1: 工具调用支持——传递 tools schema 给 LLM
        if tools_schema:
            kwargs["tools"] = tools_schema
            kwargs["tool_choice"] = req.tool_choice

        result = await litellm.acompletion(**kwargs)

        # Phase 3: 通过 adapter 标准化响应
        normalized = adapter.normalize_response(result, model)
        usage = self._build_usage(model, result.usage)

        return LLMResponse(
            content=normalized["content"],
            model=model,
            usage=usage,
            tool_calls=normalized.get("tool_calls"),
            stop_reason=normalized.get("stop_reason", "end_turn"),
            provider_adapter=adapter.provider_name,
        )

    async def generate_stream(self, req, task_id, entropy_monitor=None):
        """旧流式方法——保留向后兼容。内部委托给 generate_stream_with_tools。"""
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

    async def generate_stream_with_tools(
        self,
        req: LLMRequest,
        task_id: str,
        agent_name: str = "",
    ):
        """流式 LLM 调用——支持工具调用（Phase 3）。

        每块返回 (StreamEventType, data) 元组的 async generator。
        对标 OpenCode fullStream——逐 token 推送 text_delta，
        finish_reason=tool_calls 时推送 tool_call 事件。

        Yields:
            (StreamEventType, dict): 流式事件类型 + 数据
        """
        from orbit.stream.events import StreamEventType

        model = self.default_model
        # Phase 3: 流式调用也经过熔断器
        try:
            await self.cb.before_call(model)
            async for event in self._stream_completion_with_tools(model, req):
                yield event
            await self.cb.record_success(model)
            return
        except Exception as e:
            await self.cb.record_failure(model)
            logger.warning("stream_primary_failed", model=model, error=str(e))

        # 降级
        model = self.fallback_model
        try:
            await self.cb.before_call(model)
            async for event in self._stream_completion_with_tools(model, req):
                yield event
            await self.cb.record_success(model)
        except Exception as e:
            await self.cb.record_failure(model)
            logger.error("stream_fallback_failed", model=model, error=str(e))
            yield (StreamEventType.ERROR, {"message": str(e), "code": "STREAM_FAILED"})

    async def _stream_completion_with_tools(self, model: str, req: LLMRequest):
        """流式 completion——支持工具 schema 和 tool_calls 解析。

        WHY 独立方法: 流式解析逻辑与同步 _do_completion 不同——
        流式下 tool_calls 在最终 chunk 聚合，需要累积所有 chunk。
        """
        import litellm

        from orbit.stream.events import StreamEventType

        # 构建消息
        if req.messages:
            messages = req.messages
        else:
            messages = [
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.prompt},
            ]

        # Phase 3: adapter 标准化
        adapter = self._get_adapter(model, req.provider)
        messages = adapter.normalize_messages(messages)
        tools_schema = adapter.normalize_tool_schema(req.tools) if req.tools else None

        kwargs: dict[str, Any] = dict(
            model=model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
        )
        if model.startswith("openai/glm"):
            kwargs["api_base"] = GLM_API_BASE
            kwargs["api_key"] = settings.ZAI_API_KEY
        if tools_schema:
            kwargs["tools"] = tools_schema
            kwargs["tool_choice"] = req.tool_choice

        stream = await litellm.acompletion(**kwargs)

        # 流式累积——tool_calls 在流式下是增量推送
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}  # index → {id, name, arguments}

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # 文本增量
            if delta.content:
                content_parts.append(delta.content)
                yield (StreamEventType.TEXT_DELTA, {"delta": delta.content})

            # 工具调用增量（流式聚合）
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.id or "",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_acc[idx]
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            acc["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            acc["function"]["arguments"] += tc.function.arguments

            # 检查 finish_reason
            finish = chunk.choices[0].finish_reason
            if finish:
                if tool_calls_acc:
                    # 推送聚合后的 tool_calls
                    tool_calls_list = []
                    for idx in sorted(tool_calls_acc.keys()):
                        tc = tool_calls_acc[idx]
                        tool_calls_list.append(
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": tc["function"],
                            }
                        )
                    yield (StreamEventType.TOOL_CALL, {"tool_calls": tool_calls_list})
                break

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
