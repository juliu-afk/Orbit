"""Step 4.3 ComplianceValidator + RuleEngine 单元测试。"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from orbit.compliance.rule_engine import (
    ComplianceRule,
    RuleEngine,
    RuleSeverity,
    RuleStatus,
)
from orbit.compliance.validator import ComplianceValidator
from orbit.knowledge.store import KnowledgeStore


class TestRuleEngine:
    """规则引擎——注册/检查/批量。"""

    def test_register_and_get(self) -> None:
        engine = RuleEngine()
        rule = ComplianceRule(
            rule_id="test-1",
            name="测试规则",
            description="测试",
            severity=RuleSeverity.INFO,
        )
        engine.register(rule)
        got = engine.get("test-1")
        assert got is not None
        assert got.name == "测试规则"

    def test_default_rules_registered(self) -> None:
        engine = RuleEngine()
        assert len(engine.list_rules()) >= 3

    def test_min_source_level_pass(self) -> None:
        rule = ComplianceRule(
            rule_id="sl",
            name="来源",
            description="",
            min_source_level=2,
        )
        assert rule.check("TEST", source_level=1) == RuleStatus.PASS  # IFRS

    def test_min_source_level_warning(self) -> None:
        rule = ComplianceRule(
            rule_id="sl",
            name="来源",
            description="",
            min_source_level=2,
            severity=RuleSeverity.WARNING,
        )
        assert rule.check("TEST", source_level=3) == RuleStatus.WARNING

    def test_min_source_level_critical_violation(self) -> None:
        rule = ComplianceRule(
            rule_id="sl",
            name="来源",
            description="",
            min_source_level=2,
            severity=RuleSeverity.CRITICAL,
        )
        assert rule.check("TEST", source_level=4) == RuleStatus.VIOLATION

    def test_keyword_check_pass(self) -> None:
        rule = ComplianceRule(
            rule_id="kw",
            name="关键词",
            description="",
            required_keywords=["衡量"],
        )
        assert rule.check("TEST", definition="衡量企业盈利能力") == RuleStatus.PASS

    def test_keyword_check_fail(self) -> None:
        rule = ComplianceRule(
            rule_id="kw",
            name="关键词",
            description="",
            required_keywords=["衡量", "度量"],
            severity=RuleSeverity.WARNING,
        )
        assert rule.check("TEST", definition="计算公式") == RuleStatus.WARNING

    def test_check_all_returns_dict(self) -> None:
        engine = RuleEngine()
        results = engine.check_all("CurrentRatio", source_level=2, definition="衡量偿债能力")
        assert len(results) >= 3
        assert all(isinstance(v, RuleStatus) for v in results.values())


class TestComplianceValidator:
    """合规验证器——validate/validate_all/降级。"""

    @pytest.fixture
    def validator(self) -> Generator[ComplianceValidator, None, None]:
        path = Path(tempfile.mktemp(suffix=".db"))
        store = KnowledgeStore(db_path=path)
        store.initialize()
        v = ComplianceValidator(store=store)
        yield v
        store.close(cleanup=True)

    def test_validate_pass(self, validator: ComplianceValidator) -> None:
        """IFRS 概念来源等级 1——通过。"""
        result = validator.validate("accounting", "EBITDA")
        assert result is not None
        assert result.passed is True

    def test_validate_warning(self, validator: ComplianceValidator) -> None:
        """CAS 概念来源等级 2——可能触发 warning。"""
        result = validator.validate("accounting", "CurrentRatio")
        assert result is not None
        # source_level=2 可能触发某些规则的 warning
        assert result.status in ("pass", "warning")

    def test_validate_not_found(self, validator: ComplianceValidator) -> None:
        """不存在的概念返回 None。"""
        assert validator.validate("accounting", "FakeConcept") is None

    def test_validate_all(self, validator: ComplianceValidator) -> None:
        """批量验证 10 个概念全返回结果。"""
        results = validator.validate_all("accounting")
        assert len(results) == 10
        for r in results:
            assert r.concept
            assert r.status in ("pass", "warning", "violation")

    def test_result_to_dict(self, validator: ComplianceValidator) -> None:
        """ComplianceResult.to_dict() 输出完整字段。"""
        result = validator.validate("accounting", "ROE")
        assert result is not None
        d = result.to_dict()
        assert d["concept"] == "ROE"
        assert "rules" in d
        assert "details" in d
        assert d["source_uri"].startswith("standard://")

    def test_list_rules(self, validator: ComplianceValidator) -> None:
        """list_rules() 返回规则列表。"""
        rules = validator.list_rules()
        assert len(rules) >= 3
        assert all("rule_id" in r for r in rules)
