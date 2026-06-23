"""E2E Mock LLM——确定性输出，可控失败。

WHY Mock 而非真实 LLM：E2E 需要稳定可重复的结果，
外部 API 波动/费用/延迟会破坏测试的确定性。
PRD+ADR Q1 决议：默认 Mock，夜间构建用真实 LLM。
"""

from __future__ import annotations

from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage


class LLMError(Exception):
    """模拟 LLM 调用失败（对应 litellm 抛出的异常）。"""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"LLM error {status_code}: {message}")


class MockLLMClient:
    """Mock LLM 客户端——实现 generate 接口，与 LLMClient 同签名。

    可配置：
    - fail_count: 前 N 次调用抛 LLMError（模拟 5xx）
    - fixed_response: 固定返回内容
    - entropy: 控制 L3 熵监控触发（>0.75 触发告警）
    """

    def __init__(
        self,
        fail_count: int = 0,
        fixed_response: str = "[mock] CODE_GENERATED_OK",
        entropy: float = 0.0,
    ) -> None:
        self.fail_count = fail_count
        self.fixed_response = fixed_response
        self.entropy = entropy
        self.call_count = 0
        # 记录调用历史，供测试断言
        self.calls: list[LLMRequest] = []

    async def generate(self, req: LLMRequest, task_id: str) -> LLMResponse:
        """Mock LLM 调用。

        Raises:
            LLMError: 前 fail_count 次调用时抛出（模拟 5xx）
        """
        self.call_count += 1
        self.calls.append(req)

        if self.call_count <= self.fail_count:
            raise LLMError(500, f"Mock LLM internal error (call #{self.call_count})")

        return LLMResponse(
            content=self.fixed_response,
            model="mock-model",
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                cost_usd=0.0,
            ),
            degraded=False,
        )
