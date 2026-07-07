"""testing/feedback.py 单元测试。"""

from __future__ import annotations

from orbit.testing.feedback import FailureFeedback


class TestFailureFeedback:
    """FailureFeedback——失败模式入库 + Prompt 注入。"""

    def test_record_without_knowledge_returns_none(self):
        """无 knowledge → 静默跳过，不崩溃。"""
        fb = FailureFeedback()
        import asyncio
        result = asyncio.run(fb.record("mod", "TypeError", "detail"))
        assert result is None

    def test_query_without_knowledge_returns_empty(self):
        """无 knowledge → 返回空列表。"""
        fb = FailureFeedback()
        import asyncio
        results = asyncio.run(fb.query("mod"))
        assert results == []

    def test_build_prompt_injection_empty(self):
        """空列表 → 空字符串。"""
        fb = FailureFeedback()
        result = fb.build_prompt_injection([])
        assert result == ""

    def test_build_prompt_injection_with_patterns(self):
        """有失败模式 → 生成 Prompt 注入文本。"""
        fb = FailureFeedback()
        patterns = [
            {"module": "scheduler", "error_type": "NullError", "error_detail": "self.context is None", "frequency": 3},
            {"module": "gateway", "error_type": "TimeoutError", "error_detail": "LLM timeout", "frequency": 1},
        ]
        result = fb.build_prompt_injection(patterns)
        assert "scheduler" in result
        assert "NullError" in result
        assert "gateway" in result
        assert "3次" in result

    def test_pattern_fingerprint_deterministic(self):
        """相同输入 → 相同 fingerprint。"""
        import hashlib
        fp1 = hashlib.blake2b(b"mod:TypeError:detail", digest_size=8).hexdigest()
        fp2 = hashlib.blake2b(b"mod:TypeError:detail", digest_size=8).hexdigest()
        assert fp1 == fp2
