"""覆盖率补测——context/relevance.py (RelevanceScorer + CodeFragment)."""

from __future__ import annotations

import pytest

from orbit.context.relevance import (
    BODY_MATCH_WEIGHT,
    CALLEE_MATCH_WEIGHT,
    EXACT_MATCH_WEIGHT,
    MAX_SOURCE_SIZE,
    SUBSTRING_MATCH_WEIGHT,
    CodeFragment,
    RelevanceScorer,
)


class TestCodeFragment:
    def test_init(self):
        cf = CodeFragment(
            identifier="calculate_tax",
            node_type="function",
            source="def calculate_tax(amount): return amount * 0.13",
            line_start=10,
            line_end=12,
            relevance_score=0.85,
        )
        assert cf.identifier == "calculate_tax"
        assert cf.node_type == "function"
        assert cf.relevance_score == 0.85

    def test_default_score(self):
        cf = CodeFragment(
            identifier="foo",
            node_type="async_function",
            source="async def foo(): pass",
            line_start=1,
            line_end=2,
            relevance_score=0.0,
        )
        assert cf.relevance_score == 0.0


class TestRelevanceScorer:
    def test_init(self):
        scorer = RelevanceScorer()
        assert scorer is not None

    def test_score_empty_source(self):
        """空源码 → 返回空列表。"""
        scorer = RelevanceScorer()
        fragments = scorer.score("", ["keyword"])
        assert fragments == []

    def test_score_no_keywords(self):
        """无关键词 → 返回空。"""
        scorer = RelevanceScorer()
        fragments = scorer.score("def foo(): pass", [])
        assert fragments == []

    def test_score_with_function(self):
        """包含匹配函数的源码 → 返回相关片段。"""
        scorer = RelevanceScorer()
        source = """
def calculate_tax(amount):
    return amount * 0.13

def unrelated_helper():
    return 42
"""
        fragments = scorer.score(source, ["tax", "calculate"])
        assert len(fragments) >= 1
        # calculate_tax 应该是最相关的
        if fragments:
            assert fragments[0].identifier == "calculate_tax"

    def test_score_with_class(self):
        """包含类的源码 → 正确提取。"""
        scorer = RelevanceScorer()
        source = """
class TaxCalculator:
    def calculate(self, amount):
        return amount * 0.13
"""
        fragments = scorer.score(source, ["Tax", "calculate"])
        assert len(fragments) >= 1

    def test_max_source_size_constant(self):
        """MAX_SOURCE_SIZE 是正数。"""
        assert MAX_SOURCE_SIZE > 0

    def test_weights_sum_valid(self):
        """权重非负。"""
        assert EXACT_MATCH_WEIGHT >= 0
        assert SUBSTRING_MATCH_WEIGHT >= 0
        assert BODY_MATCH_WEIGHT >= 0
        assert CALLEE_MATCH_WEIGHT >= 0
        assert EXACT_MATCH_WEIGHT > SUBSTRING_MATCH_WEIGHT  # 精确匹配权重大于子串
