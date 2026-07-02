"""边界规则引擎 单元测试。"""

from orbit.brief.boundaries import BoundaryEngine, DEFAULT_RULES
from orbit.brief.models import BoundaryRule


class TestBoundaryEngine:
    def test_default_rules_loaded(self) -> None:
        engine = BoundaryEngine()
        assert len(engine.rules) > 0
        rule_ids = {r.rule_id for r in engine.rules}
        assert "no-eval" in rule_ids
        assert "no-sql-injection" in rule_ids
        assert "no-hardcoded-secrets" in rule_ids

    def test_add_custom_rule(self) -> None:
        engine = BoundaryEngine()
        custom = BoundaryRule(
            rule_id="no-float-money",
            description="金额用 Decimal",
            severity="error",
            category="finance",
            enforcement={"static_analysis": {"ruff_rules": ["S301"]}},
        )
        engine.add_rule(custom)
        assert len(engine.rules) == len(DEFAULT_RULES) + 1
        rule_ids = {r.rule_id for r in engine.rules}
        assert "no-float-money" in rule_ids

    def test_add_duplicate_rule_ignored(self) -> None:
        engine = BoundaryEngine()
        original_count = len(engine.rules)
        dup = BoundaryRule(rule_id="no-eval", description="dup")
        engine.add_rule(dup)
        assert len(engine.rules) == original_count

    def test_add_rules_batch(self) -> None:
        engine = BoundaryEngine()
        customs = [
            BoundaryRule(rule_id="custom-1", description="C1"),
            BoundaryRule(rule_id="custom-2", description="C2"),
        ]
        engine.add_rules(customs)
        assert len(engine.rules) == len(DEFAULT_RULES) + 2

    def test_generate_rules_yaml(self) -> None:
        engine = BoundaryEngine()
        yaml_text = engine.generate_rules_yaml()
        assert "version: \"1.0\"" in yaml_text
        assert "no-eval" in yaml_text
        assert "no-sql-injection" in yaml_text
        assert "rules:" in yaml_text

    def test_generate_ruff_config(self) -> None:
        engine = BoundaryEngine()
        ruff_config = engine.generate_ruff_config()
        assert "[lint]" in ruff_config
        assert "select =" in ruff_config
        # 应该包含默认规则的 ruff 规则
        assert "S307" in ruff_config  # no-eval

    def test_generate_pre_commit_hooks(self) -> None:
        engine = BoundaryEngine()
        hooks = engine.generate_pre_commit_hooks()
        assert len(hooks) > 0
        hook_ids = [h["id"] for h in hooks]
        assert "ruff" in hook_ids  # ruff hook always present if rules use ruff

    def test_generate_review_checklist(self) -> None:
        engine = BoundaryEngine()
        checklist = engine.generate_review_checklist()
        assert len(checklist) > 0
        # 每条检查应包含严重性标签
        for item in checklist:
            assert item.startswith("[ERROR]") or item.startswith("[WARNING]")
            assert ":" in item

    def test_empty_rules_generate_minimal_output(self) -> None:
        """无规则时的边界情况。"""
        engine = BoundaryEngine()
        engine._rules = []  # 清空
        ruff = engine.generate_ruff_config()
        assert ruff == ""
        hooks = engine.generate_pre_commit_hooks()
        assert hooks == []

    def test_rule_with_grep_pattern_generates_hook(self) -> None:
        engine = BoundaryEngine()
        engine.add_rule(
            BoundaryRule(
                rule_id="no-print-debug",
                description="禁止 print 调试",
                severity="warning",
                category="style",
                enforcement={
                    "static_analysis": {"grep_pattern": r"print\(.*debug"},
                    "pre_commit": True,
                },
            )
        )
        hooks = engine.generate_pre_commit_hooks()
        grep_hooks = [h for h in hooks if h["id"] == "orbit-no-print-debug"]
        assert len(grep_hooks) == 1
        assert "grep" in grep_hooks[0]["entry"]


class TestDefaultRules:
    def test_all_default_rules_have_ids(self) -> None:
        for rule in DEFAULT_RULES:
            assert rule.rule_id, f"规则缺少 ID: {rule}"
            assert rule.description, f"规则缺少描述: {rule}"
            assert rule.severity in ("error", "warning")
            assert rule.category

    def test_security_rules_are_errors(self) -> None:
        security_rules = [r for r in DEFAULT_RULES if r.category == "security"]
        for rule in security_rules:
            assert rule.severity == "error", f"安全规则应为 error: {rule.rule_id}"
            assert rule.enforcement.get("pre_commit"), f"安全规则应有 pre_commit: {rule.rule_id}"
