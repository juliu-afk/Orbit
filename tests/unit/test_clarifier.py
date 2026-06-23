"""Step 0.3 Phase0——需求澄清引擎单元测试。"""

from orbit.scheduler.clarifier import ClarificationEngine


class TestClarificationEngine:
    """需求澄清——完整性/矛盾/评分。"""

    def test_complete_prd_scores_high(self) -> None:
        """完整 PRD → 高分通过。"""
        prd = """
        目标: 构建支付网关
        范围: 包含支付/退款/查询, 不包含风控
        验收标准: 支付成功率≥99%, 延迟<200ms
        性能: 支持 1000 QPS
        边界条件: 超时重试 3 次, 降级返回缓存
        """
        engine = ClarificationEngine()
        result = engine.clarify(prd)
        assert result.passed is True
        assert result.score >= 60

    def test_incomplete_prd_scores_low(self) -> None:
        """缺失多字段 → 低分。"""
        prd = "做一个网站"
        engine = ClarificationEngine()
        result = engine.clarify(prd)
        assert result.score < 60

    def test_contradiction_detected(self) -> None:
        """互斥约束 → blocking issue。"""
        prd = "必须支持离线模式, 同时必须实时同步所有数据"
        engine = ClarificationEngine()
        result = engine.clarify(prd)
        contradictions = [i for i in result.issues if i.type == "contradiction"]
        assert len(contradictions) >= 1

    def test_no_contradiction_clean(self) -> None:
        """无矛盾 PRD → 无 contradiction issue。"""
        prd = "目标: 实时同步, 范围: 仅在线模式, 验收: 延迟<100ms"
        engine = ClarificationEngine()
        result = engine.clarify(prd)
        contradictions = [i for i in result.issues if i.type == "contradiction"]
        assert len(contradictions) == 0

    def test_missing_fields_reported(self) -> None:
        """缺失字段 → warning issues + completeness 标记。"""
        prd = "目标: 计算器"
        engine = ClarificationEngine()
        result = engine.clarify(prd)
        assert result.completeness["has_目标"] is True
        assert result.completeness["has_验收标准"] is False
        missing = [i for i in result.issues if i.type == "missing_field"]
        assert len(missing) >= 1

    def test_score_below_40_blocked(self) -> None:
        """评分 <40 → passed=False。"""
        engine = ClarificationEngine()
        result = engine.clarify("")
        assert result.passed is False
        assert result.score < 40

    def test_to_dict_includes_all_keys(self) -> None:
        engine = ClarificationEngine()
        result = engine.clarify("目标: test\n范围: 测试\n验收: 通过测试")
        d = result.to_dict()
        assert "score" in d
        assert "passed" in d
        assert "issues" in d
        assert "completeness" in d
