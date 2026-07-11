import pytest
class TestGatewaySchemas:
    def test_req(self):
        from orbit.gateway.schemas import LLMRequest
        assert LLMRequest(prompt="t", tier=1, max_tokens=100).prompt=="t"
    def test_resp(self):
        from orbit.gateway.schemas import LLMResponse, LLMUsage
        u = LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30, cost_usd=0.0)
        assert LLMResponse(content="r", model="m", usage=u, degraded=False).content=="r"
class TestRouter:
    def test_agent(self):
        from orbit.router.agent import RouterAgent
        assert RouterAgent() is not None
    def test_bandit(self):
        from orbit.router.bandit import ThompsonBandit
        assert ThompsonBandit() is not None
