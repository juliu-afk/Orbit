"""V15.1 多模态 P0：VisionAdapter——httpx 直连多模态 API。

WHY 绕过 LiteLLM：LiteLLM 对 GLM-4.1V/GLM-4.6V 多模态支持滞后。
OpenAI 兼容端点直接 httpx 调用，更简单、更可控。

降级策略（在此层实现）：
  T3 失败 → T2 → 失败则抛 MultimodalAPIError（不降级到纯文本）

WHY 独立 adapter 而非扩展 OpenAIAdapter：
  - 多模态 payload 格式不同（content array vs string prompt）
  - 降级逻辑独立
  - P1 多 provider 时更容易扩展
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from orbit.core.config import settings
from orbit.gateway.multimodal import Tier, TierConfig, TierRouter, TIERS
from orbit.gateway.schemas import LLMResponse, LLMUsage

logger = structlog.get_logger("orbit.gateway.adapters.vision")


class MultimodalAPIError(Exception):
    """多模态 API 调用失败——所有重试/降级路径已耗尽。"""

    def __init__(self, message: str, tier: Tier | None = None, status_code: int | None = None):
        super().__init__(message)
        self.tier = tier
        self.status_code = status_code


class VisionAdapter:
    """多模态 HTTP 适配器。

    职责：构建 OpenAI 兼容 payload → 发送 → 解析响应 → LLMResponse。
    不做：梯度判定（交给 TierRouter）、工具调用（P1）。
    """

    def __init__(self, api_key: str | None = None):
        # WHY 从参数/环境取 key：测试时可注入，生产用 settings
        self.api_key = api_key or settings.ZAI_API_KEY
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """延迟创建 httpx client——避免导入时网络检查。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_connections=10),
            )
        return self._client

    async def close(self):
        """关闭 HTTP client——测试/服务关闭时调用。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        tier: Tier,
        config: TierConfig | None = None,
        content: list[dict] | None = None,
        prompt: str = "",
        max_tokens: int | None = None,
        system_prompt: str = "",
    ) -> LLMResponse:
        """发送多模态请求到指定梯度的模型。

        Args:
            tier: 梯度（Tier.LIGHT/STANDARD/HEAVY）——用于降级链
            config: TierConfig（可选，None=从 TIERS 自动获取）
            content: 多模态 content array
            prompt: 附加文本提示词
            max_tokens: 覆盖默认 max_tokens
            system_prompt: 系统提示词（作为 messages[0] 的 system role）

        Returns:
            LLMResponse——统一格式

        Raises:
            MultimodalAPIError: 调用失败（含降级历史）
        """
        if config is None:
            config = TierRouter.get_config(tier)
        if content is None:
            content = []
        return await self._generate_with_downgrade(
            tier, config, content, prompt, max_tokens, system_prompt, []
        )

    async def _generate_with_downgrade(
        self,
        tier: Tier,
        config: TierConfig,
        content: list[dict],
        prompt: str,
        max_tokens: int | None,
        system_prompt: str,
        downgrade_history: list[str],
    ) -> LLMResponse:
        """内部方法——处理当前配置 + 失败时降级递归。

        WHY tier 显式传递：避免从 TierConfig 反查 Tier（脆弱设计——P1-1 修复）。
        """
        t0 = time.monotonic()

        # ── 构造 OpenAI 兼容 payload ──
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages_content = list(content)  # 浅拷贝
        if prompt:
            messages_content.append({"type": "text", "text": prompt})

        messages.append({"role": "user", "content": messages_content})

        body: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "max_tokens": max_tokens or config.max_tokens,
        }

        # GLM-4.1V thinking 参数
        if config.thinking is not None:
            body["thinking"] = {"type": "enabled" if config.thinking else "disabled"}

        client = await self._get_client()
        try:
            resp = await client.post(
                f"{config.endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except httpx.TimeoutException as e:
            logger.warning("vision_timeout", model=config.model, timeout_sec=time.monotonic() - t0)
            return await self._downgrade_or_raise(
                tier, config, content, prompt, max_tokens, system_prompt, downgrade_history,
                f"超时 ({time.monotonic() - t0:.1f}s)"
            )
        except httpx.TransportError as e:
            logger.warning("vision_transport_error", model=config.model, error=str(e))
            return await self._downgrade_or_raise(
                tier, config, content, prompt, max_tokens, system_prompt, downgrade_history,
                f"连接错误: {e}"
            )

        elapsed = time.monotonic() - t0

        # ── 处理非 200 响应 ──
        if resp.status_code != 200:
            error_msg = self._extract_error(resp)
            logger.warning(
                "vision_api_error",
                model=config.model,
                status=resp.status_code,
                error=error_msg,
                elapsed=elapsed,
            )
            # 429/5xx → 可降级；4xx（非 429）→ 不可降级（请求错误）
            if resp.status_code in (429, 500, 502, 503, 504):
                return await self._downgrade_or_raise(
                    tier, config, content, prompt, max_tokens, system_prompt, downgrade_history,
                    f"API 错误 {resp.status_code}: {error_msg}"
                )
            raise MultimodalAPIError(
                f"请求错误 {resp.status_code}: {error_msg}",
                status_code=resp.status_code,
            )

        # ── 解析成功响应 ──
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        usage_data = data.get("usage", {})

        usage = LLMUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            cost_usd=self._calculate_cost(config, usage_data),
        )

        logger.info(
            "vision_call_ok",
            model=config.model,
            tokens=usage.total_tokens,
            cost=usage.cost_usd,
            elapsed=elapsed,
            downgrade_count=len(downgrade_history),
        )

        return LLMResponse(
            content=msg.get("content", ""),
            model=data.get("model", config.model),
            usage=usage,
            model_source=f"multimodal_tier_{config.description[:20]}",
            degraded=len(downgrade_history) > 0,
            stop_reason=choice.get("finish_reason", "end_turn"),
            provider_adapter="vision",
        )

    async def _downgrade_or_raise(
        self,
        tier: Tier,
        failed_config: TierConfig,
        content: list[dict],
        prompt: str,
        max_tokens: int | None,
        system_prompt: str,
        history: list[str],
        reason: str,
    ) -> LLMResponse:
        """尝试降级到下一个梯度，或抛出异常。

        WHY tier 显式传递（P1-1 修复）：不再从 TierConfig 反查 Tier，
        避免 model+thinking 双匹配的脆弱设计。
        """
        history.append(f"{failed_config.model}: {reason}")

        downgrade_tier = TierRouter.get_downgrade(tier)
        if downgrade_tier is None:
            raise MultimodalAPIError(
                f"多模态调用失败，无更多降级路径。降级链: {' → '.join(history)}"
            )

        downgrade_config = TierRouter.get_config(downgrade_tier)
        logger.info(
            "vision_downgrade",
            from_tier=tier.value,
            to_tier=downgrade_tier.value,
            from_model=failed_config.model,
            to_model=downgrade_config.model,
            reason=reason,
        )

        return await self._generate_with_downgrade(
            downgrade_tier, downgrade_config, content, prompt, max_tokens, system_prompt, history
        )

    @staticmethod
    def _extract_error(resp: httpx.Response) -> str:
        """从响应的错误信息。"""
        try:
            data = resp.json()
            err = data.get("error", {})
            return str(err.get("message", err.get("code", resp.text[:200])))
        except Exception:
            return resp.text[:200]

    @staticmethod
    def _calculate_cost(config: TierConfig, usage_data: dict) -> float:
        """计算本次调用成本（美元）。

        WHY 从 config 读取定价（P2-3 修复）：不再硬编码单价和汇率。
        定价源统一在 multimodal.py 的 TierConfig 中维护。
        """
        if config.cost_per_million == 0:
            return 0.0

        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)

        # 从 TierConfig 读取（CNY 元/百万 tokens）→ 转为 USD
        # 汇率从 settings 读取，兜底 7.2
        from orbit.core.config import settings
        rate = getattr(settings, "USD_CNY_RATE", 7.2)

        input_cost = (prompt_tokens / 1_000_000) * config.input_cost_per_million / rate
        output_cost = (completion_tokens / 1_000_000) * config.output_cost_per_million / rate

        return round(input_cost + output_cost, 6)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
