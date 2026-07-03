"""complexity.py 测试——ComplexityScorer + find_similar_task.

覆盖:
- ComplexityResult.to_dict
- ComplexityScorer.evaluate: 简单/复杂关键词, 文件数, scope, 核心模块, 风险, 钳制
- find_similar_task: 空历史, 空 bigrams, 阈值
"""

from __future__ import annotations

from orbit.scheduler.complexity import ComplexityResult, ComplexityScorer, find_similar_task


# ── ComplexityResult ──────────────────────────────────────


def test_to_dict() -> None:
    r = ComplexityResult(
        score=42, file_count=3, scope="multi_file", risk="medium",
        is_core=True, recommended_mode="full", reasons=["核心模块"],
    )
    d = r.to_dict()
    assert d["score"] == 42
    assert d["scope"] == "multi_file"
    assert d["reasons"] == ["核心模块"]

    r2 = ComplexityResult(score=10, file_count=1, scope="single_file", risk="low", is_core=False, recommended_mode="fast")
    assert r2.to_dict()["recommended_mode"] == "fast"


# ── ComplexityScorer.evaluate ─────────────────────────────


def test_empty_text() -> None:
    """空文本基准分 50."""
    r = ComplexityScorer().evaluate("")
    assert r.score == 50
    assert r.recommended_mode == "full"


def test_simple_keyword_lowers() -> None:
    """简单关键词拉低分数."""
    r = ComplexityScorer().evaluate("改一下日志级别")
    assert r.score < 50


def test_complex_keyword_raises() -> None:
    """复杂关键词推高分数."""
    r = ComplexityScorer().evaluate("重构支付模块架构")
    assert r.score > 50


def test_simple_plus_complex() -> None:
    """简单+复杂关键词综合叠加."""
    r = ComplexityScorer().evaluate("改一行日志 重构架构")
    # 简单匹配: 改一行 → -25; 复杂匹配: 重构+30, 架构+30
    # 50 - 25 + 30 + 30 = 85
    assert r.score > 50


def test_core_module_raises() -> None:
    """核心模块检测加分."""
    r = ComplexityScorer().evaluate("修改 voucher 过账逻辑")
    assert r.is_core is True
    assert r.score >= 50  # 50 + 20(核心) - 20(修改) = 50


def test_scope_single_line() -> None:
    """含"一行"的文本 scope 为 single_line."""
    r = ComplexityScorer().evaluate("改一行配置")
    assert r.scope == "single_line"


def test_scope_single_line_variable() -> None:
    """含"这个变量"的文本 scope 为 single_line."""
    r = ComplexityScorer().evaluate("修改这个变量的名字")
    assert r.scope == "single_line"


def test_scope_multi_module_by_file_count() -> None:
    """批量/所有等词 → file_count=5 → scope multi_module."""
    r = ComplexityScorer().evaluate("修改所有配置")
    assert r.file_count == 5
    assert r.scope == "multi_module"


def test_scope_single_file_default() -> None:
    """默认 2 文件 → scope single_file."""
    r = ComplexityScorer().evaluate("实现新功能")
    assert r.file_count == 2
    assert r.scope == "single_file"


def test_scope_single_file_by_indicator() -> None:
    """含"一个" → file_count=1 → scope single_file."""
    r = ComplexityScorer().evaluate("修改一个配置")
    assert r.file_count == 1
    assert r.scope == "single_file"


def test_risk_high() -> None:
    """核心模块 + 文件 ≥3 → high."""
    r = ComplexityScorer().evaluate("重构 double_entry 所有模块")
    assert r.risk == "high"


def test_risk_medium_core() -> None:
    """核心模块但文件少 → medium."""
    r = ComplexityScorer().evaluate("修改 voucher 注释")
    assert r.is_core is True
    assert r.risk == "medium"


def test_risk_medium_large_file_set() -> None:
    """文件数 ≥5 但非核心 → medium."""
    r = ComplexityScorer().evaluate("格式化所有文件")
    assert r.risk == "medium"


def test_risk_low() -> None:
    """非核心 + 文件少 → low."""
    r = ComplexityScorer().evaluate("格式化代码")
    assert r.risk == "low"


def test_clamp_min_zero() -> None:
    """分数不低于 0."""
    r = ComplexityScorer().evaluate("改一行注释修拼写")
    assert r.score >= 0


def test_clamp_max_100() -> None:
    """分数不超过 100."""
    r = ComplexityScorer().evaluate("重构架构 实现支付 重构架构 实现支付 重构架构 实现支付")
    assert r.score <= 100


def test_file_count_batch() -> None:
    """批量指示器 → 5."""
    assert ComplexityScorer().evaluate("批量处理").file_count == 5


def test_file_count_single() -> None:
    """单个指示器 → 1."""
    assert ComplexityScorer().evaluate("修改一个文件").file_count == 1


def test_file_count_default_two() -> None:
    """无指示器 → 2."""
    assert ComplexityScorer().evaluate("随便改改").file_count == 2


def test_fast_lane_threshold() -> None:
    """score < 30 → fast."""
    r = ComplexityScorer().evaluate("修拼写")
    assert r.recommended_mode == "fast"


def test_full_when_above_threshold() -> None:
    """score ≥ 30 → full."""
    r = ComplexityScorer().evaluate("实现支付功能")
    assert r.recommended_mode == "full"


# ── find_similar_task ─────────────────────────────────────


def test_find_similar_empty_history() -> None:
    assert find_similar_task("hello", []) is None


def test_find_similar_no_match_low_threshold() -> None:
    assert find_similar_task("abc", ["xyz"], threshold=0.99) is None


def test_find_similar_exact_match() -> None:
    assert find_similar_task("hello world", ["hello world"], threshold=0.5) == "hello world"


def test_find_similar_partial_match() -> None:
    result = find_similar_task("implement login", ["implement login page", "fix bug"], threshold=0.3)
    assert result is not None


def test_find_similar_empty_bigrams() -> None:
    """单字符文本无 bigrams."""
    assert find_similar_task("a", ["hello"], threshold=0.0) is None


def test_find_similar_history_single_char_skipped() -> None:
    """历史中含单个字符（无 bigrams）跳过."""
    result = find_similar_task("hello", ["a", "hello"], threshold=0.5)
    assert result is not None


def test_find_similar_threshold_controls() -> None:
    assert find_similar_task("hello world", ["hello"], threshold=0.99) is None


def test_find_similar_best_match() -> None:
    """多个历史项中选最佳."""
    result = find_similar_task("修复 bug", ["加个日志", "修复 bug 问题", "重构"], threshold=0.3)
    assert result == "修复 bug 问题"


def test_find_similar_high_threshold_exact() -> None:
    """完全相同文本高阈值匹配."""
    assert find_similar_task("update README", ["update README"], threshold=0.9) == "update README"
