"""ProviderAdapter 单元测试——Anthropic + OpenAI schema 标准化.

Phase 3 组 1 (AC18): 覆盖 normalize_tool_schema / normalize_response / normalize_stop_reason.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestProviderAdapterBase:
    """ProviderAdapter ABC 默认行为。"""

    def test_default_normalize_tool_schema_passthrough(self):
        from orbit.gateway.adapters import ProviderAdapter

        class NoopAdapter(ProviderAdapter):
            provider_name = "noop"

            def normalize_response(self, raw, model):
                return {"content": "", "tool_calls": None, "stop_reason": "end_turn"}

        adapter = NoopAdapter()
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        assert adapter.normalize_tool_schema(tools) == tools

    def test_default_normalize_messages_passthrough(self):
        from orbit.gateway.adapters import ProviderAdapter

        class NoopAdapter(ProviderAdapter):
            provider_name = "noop"

            def normalize_response(self, raw, model):
                return {"content": "", "tool_calls": None, "stop_reason": "end_turn"}

        adapter = NoopAdapter()
        msgs = [{"role": "user", "content": "hello"}]
        assert adapter.normalize_messages(msgs) == msgs

    def test_normalize_stop_reason_stop(self):
        from orbit.gateway.adapters import ProviderAdapter
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        assert adapter.normalize_stop_reason("stop") == "end_turn"

    def test_normalize_stop_reason_length(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        assert adapter.normalize_stop_reason("length") == "max_tokens"

    def test_normalize_stop_reason_content_filter(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        assert adapter.normalize_stop_reason("content_filter") == "error"

    def test_normalize_stop_reason_none(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        assert adapter.normalize_stop_reason(None) == "end_turn"


class TestAnthropicAdapter:
    """Anthropic adapter 响应标准化。"""

    def test_normalize_response_no_tool_calls(self):
        from orbit.gateway.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = "Hello Claude"
        mock.choices[0].message.tool_calls = None  # type: ignore
        mock.choices[0].finish_reason = "end_turn"

        result = adapter.normalize_response(mock, "anthropic/claude-fable-5")
        assert result["content"] == "Hello Claude"
        assert result["tool_calls"] is None
        assert result["stop_reason"] == "end_turn"

    def test_normalize_response_with_tool_calls(self):
        from orbit.gateway.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = ""
        tc = MagicMock()
        tc.id = "tool_123"
        tc.function.name = "read_file"
        tc.function.arguments = '{"path":"test.py"}'
        mock.choices[0].message.tool_calls = [tc]
        mock.choices[0].finish_reason = "tool_use"

        result = adapter.normalize_response(mock, "anthropic/claude-fable-5")
        assert result["tool_calls"] is not None
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "read_file"
        # tool_calls + empty content → stop_reason = "tool_calls"
        assert result["stop_reason"] == "tool_calls"

    def test_provider_name(self):
        from orbit.gateway.adapters.anthropic import AnthropicAdapter

        assert AnthropicAdapter().provider_name == "anthropic"


class TestOpenAIAdapter:
    """OpenAI adapter 响应标准化。"""

    def test_normalize_response_no_tool_calls(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = "Hello"
        mock.choices[0].message.tool_calls = None  # type: ignore
        mock.choices[0].finish_reason = "stop"

        result = adapter.normalize_response(mock, "openai/gpt-4.1")
        assert result["content"] == "Hello"
        assert result["tool_calls"] is None
        assert result["stop_reason"] == "end_turn"

    def test_normalize_response_with_tool_calls(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = None
        tc = MagicMock()
        tc.id = "call_abc"
        tc.function.name = "write_file"
        tc.function.arguments = '{"path":"out.py","content":"..."}'
        mock.choices[0].message.tool_calls = [tc]
        mock.choices[0].finish_reason = "tool_calls"

        result = adapter.normalize_response(mock, "openai/gpt-4.1")
        assert result["tool_calls"] is not None
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "call_abc"
        assert result["stop_reason"] == "tool_calls"

    def test_normalize_response_max_tokens(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = "..."
        mock.choices[0].message.tool_calls = None  # type: ignore
        mock.choices[0].finish_reason = "length"

        result = adapter.normalize_response(mock, "openai/gpt-4.1")
        assert result["stop_reason"] == "max_tokens"

    def test_provider_name(self):
        from orbit.gateway.adapters.openai import OpenAIAdapter

        assert OpenAIAdapter().provider_name == "openai"

    def test_normalize_tool_schema_passthrough(self):
        """OpenAI adapter 不透传工具 schema（默认 no-op）。"""
        from orbit.gateway.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        tools = [{"type": "function", "function": {"name": "test"}}]
        assert adapter.normalize_tool_schema(tools) == tools
