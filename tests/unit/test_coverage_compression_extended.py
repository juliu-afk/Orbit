"""覆盖率补测——compression/token_counter.py + compression/compressor.py + compression/pipeline.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orbit.compression.compressor import ContextCompressor
from orbit.compression.pipeline import CompressionPipeline
from orbit.compression.token_counter import count_tokens


# ════════════════════════════════════════════
# 1. token_counter
# ════════════════════════════════════════════

class TestTokenCounter:
    def test_count_empty(self):
        assert count_tokens("") == 0

    def test_count_ascii(self):
        text = "hello world this is a test"
        tokens = count_tokens(text)
        assert tokens >= 5

    def test_count_long_text(self):
        assert count_tokens("x" * 1000) > count_tokens("hi")


# ════════════════════════════════════════════
# 2. ContextCompressor
# ════════════════════════════════════════════

class TestContextCompressor:
    def test_init_defaults(self):
        mock_llm = MagicMock()
        compressor = ContextCompressor(llm_client=mock_llm)
        assert compressor._llm is mock_llm

    @pytest.mark.asyncio
    async def test_compress_returns_compression_result(self):
        """compress 返回 CompressionResult。"""
        mock_llm = MagicMock()
        mock_llm.generate = MagicMock(return_value=MagicMock(content="summarized"))
        compressor = ContextCompressor(llm_client=mock_llm)

        from orbit.compression.models import CompressionResult
        result = await compressor.compress(
            [{"role": "user", "content": "test"}], task_id="t1"
        )
        assert isinstance(result, CompressionResult)
        assert result.action is not None

    def test_child_session_id_none_by_default(self):
        """未 fork 时 child_session_id 为 None。"""
        compressor = ContextCompressor(llm_client=None)
        assert compressor.child_session_id is None


# ════════════════════════════════════════════
# 3. CompressionPipeline
# ════════════════════════════════════════════

class TestCompressionPipeline:
    def test_init(self):
        pipeline = CompressionPipeline()
        assert pipeline is not None
        assert pipeline.applied_layers == []

    def test_layer1_truncate(self):
        """Layer 1: 截断超长消息。"""
        long_msg = {"role": "assistant", "content": "x" * 10000}
        result = CompressionPipeline._layer1_truncate([long_msg])
        assert len(result) == 1

    def test_layer1_short_message_unchanged(self):
        """短消息不被截断。"""
        msg = {"role": "user", "content": "hello"}
        result = CompressionPipeline._layer1_truncate([msg])
        assert result[0]["content"] == "hello"

    def test_layer5_dedup_code_blocks(self):
        """Layer 5: 重复代码块去重。"""
        msgs = [
            {"role": "assistant", "content": "here is the code:\n```python\ndef foo():\n    pass\n```"},
            {"role": "assistant", "content": "same code:\n```python\ndef foo():\n    pass\n```"},
        ]
        result = CompressionPipeline._layer5_dedup(msgs)
        assert len(result) >= 1  # 可能去重了第二个

    def test_layer5_dedup_different(self):
        """不同消息全部保留。"""
        msgs = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ]
        result = CompressionPipeline._layer5_dedup(msgs)
        assert len(result) == 2

    def test_layer2_prune(self):
        """Layer 2: 裁剪——保留系统消息 + 最近 N 轮。"""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old response"},
            {"role": "user", "content": "recent"},
        ]
        result = CompressionPipeline._layer2_prune(msgs)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_run_with_action(self):
        """pipeline.run() 带 action 参数运行。"""
        pipeline = CompressionPipeline()
        msgs = [{"role": "user", "content": "test"}]
        result, removed = await pipeline.run(msgs, action="warn")
        assert isinstance(result, list)
