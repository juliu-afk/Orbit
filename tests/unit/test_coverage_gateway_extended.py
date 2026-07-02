"""覆盖率补测——gateway/client.py + gateway/schemas.py (208行, 54%→75%)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.gateway.client import LLMClient, MODEL_FLASH, MODEL_GLM5, MODEL_PRO
from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage


# ════════════════════════════════════════════
# 1. LLM schemas
# ════════════════════════════════════════════

class TestLLMSchemas:
    def test_llm_usage_defaults(self):
        """LLMUsage 默认值正确。"""
        usage = LLMUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_llm_response_has_content(self):
        """LLMResponse 包含 content。"""
        resp = LLMResponse(
            content="hello world", model="test-model",
            usage=LLMUsage(prompt_tokens=5, completion_tokens=10),
        )
        assert resp.content == "hello world"
        assert resp.model == "test-model"

    def test_llm_request_basic(self):
        """LLMRequest 基本构造。"""
        req = LLMRequest(prompt="write code", system_prompt="be helpful")
        assert req.prompt == "write code"
        assert req.system_prompt == "be helpful"
        assert req.temperature == 0.2  # 默认

    def test_llm_request_optional_fields(self):
        """LLMRequest 可选字段。"""
        req = LLMRequest(
            prompt="test",
            temperature=0.3,
            max_tokens=500,
            provider="anthropic",
        )
        assert req.temperature == 0.3
        assert req.max_tokens == 500
        assert req.provider == "anthropic"


# ════════════════════════════════════════════
# 2. LLMClient
# ════════════════════════════════════════════

class TestLLMClient:
    def test_init_default_model(self):
        """LLMClient 默认模型。"""
        client = LLMClient()
        assert client.default_model is not None

    def test_init_custom_model(self):
        """自定义模型名。"""
        client = LLMClient(default_model="custom-model")
        assert client.default_model == "custom-model"

    def test_model_constants_non_empty(self):
        """模型常量非空。"""
        assert MODEL_FLASH
        assert MODEL_PRO
        assert MODEL_GLM5

    def test_get_usage_stats_empty(self):
        """无调用记录时 get_usage_stats 返回 0。"""
        client = LLMClient()
        stats = client.get_usage_stats("nonexistent-task")
        assert stats is not None
        assert stats.prompt_tokens == 0

    def test_init_with_provider(self):
        """带 provider 参数初始化。"""
        client = LLMClient(default_model="claude-sonnet-5")
        assert "claude" in client.default_model.lower() or "sonnet" in client.default_model.lower()


# ════════════════════════════════════════════
# 3. LLMRequest + router_decision 深度
# ════════════════════════════════════════════

class TestLLMRequestAdvanced:
    def test_request_with_tools(self):
        """LLMRequest 支持 tools 参数。"""
        tools = [{"name": "read_file", "description": "read a file"}]
        req = LLMRequest(prompt="read file.txt", tools=tools)
        assert len(req.tools) == 1
        assert req.tools[0]["name"] == "read_file"

    def test_request_with_messages(self):
        """LLMRequest 支持 messages（多轮对话）。"""
        msgs = [{"role": "user", "content": "hello"}]
        req = LLMRequest(prompt="continue", messages=msgs)
        assert len(req.messages) == 1
        assert req.messages[0]["role"] == "user"
