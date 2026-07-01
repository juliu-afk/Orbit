"""Compliance rule engine 单元测试。"""
from orbit.compliance.rule_engine import RuleEngine

def test_engine_init():
    e = RuleEngine()
    assert e is not None

def test_list_rules():
    e = RuleEngine()
    rules = e.list_rules()
    assert isinstance(rules, list)
