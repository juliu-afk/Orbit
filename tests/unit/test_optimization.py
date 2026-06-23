"""Step O1+O2——系统优化单元测试。"""

from orbit.scheduler.complexity import ComplexityScorer, find_similar_task


class TestComplexityScorer:
    """复杂度评分——简单任务低分/复杂任务高分/快车道路由。"""

    def test_simple_task_scores_low(self) -> None:
        scorer = ComplexityScorer()
        r = scorer.evaluate("把日志级别改成debug")
        assert r.score < 50
        assert r.recommended_mode == "fast" or r.score < ComplexityScorer.FAST_LANE_THRESHOLD + 20

    def test_complex_task_scores_high(self) -> None:
        scorer = ComplexityScorer()
        r = scorer.evaluate("实现支付网关，包含退款和查询功能，需修改数据库schema")
        assert r.score >= 40  # 复杂任务应高于阈值

    def test_core_module_detected(self) -> None:
        scorer = ComplexityScorer()
        r = scorer.evaluate("修改 scheduler 的 orchestration 逻辑")
        assert r.is_core is True

    def test_single_file_lowers_score(self) -> None:
        scorer = ComplexityScorer()
        r_simple = scorer.evaluate("改一行配置")
        r_complex = scorer.evaluate("实现分布式事务系统，重构数据库层")
        assert r_simple.score < r_complex.score

    def test_result_to_dict(self) -> None:
        scorer = ComplexityScorer()
        r = scorer.evaluate("加个日志")
        d = r.to_dict()
        assert "score" in d
        assert "recommended_mode" in d
        assert "scope" in d


class TestHistoryReuse:
    """历史相似度——匹配/不匹配。"""

    def test_exact_match(self) -> None:
        history = ["把日志级别改成debug"]
        result = find_similar_task("把日志级别改成debug", history)
        assert result == "把日志级别改成debug"

    def test_near_match(self) -> None:
        history = ["把日志级别修改成debug"]
        result = find_similar_task("把日志级别改成debug", history)
        # 仅差 "修改" vs "改"——高相似度应匹配
        assert result is not None

    def test_no_match_different_topics(self) -> None:
        history = ["实现支付网关"]
        result = find_similar_task("改日志级别", history)
        assert result is None

    def test_empty_history(self) -> None:
        assert find_similar_task("test", []) is None

    def test_low_threshold_blocks(self) -> None:
        history = ["改日志级别"]
        result = find_similar_task("完全不同的话题内容很长文本", history, threshold=0.95)
        assert result is None
