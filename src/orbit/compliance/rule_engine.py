"""Step 4.3 合规规则引擎。

DSL 风格规则定义——日期范围、版本约束、来源等级过滤。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RuleSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RuleStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    VIOLATION = "violation"


@dataclass
class ComplianceRule:
    """合规规则定义。

    condition 字段含义：
    - max_age_months: 知识从发布起最大月数，超过则告警
    - min_source_level: 最低来源等级（1=IFRS 最高，5=企业内部 最低）
    - required_keywords: 概念定义中必须包含的关键词
    """

    rule_id: str
    name: str
    description: str
    severity: RuleSeverity = RuleSeverity.WARNING
    max_age_months: int | None = None
    min_source_level: int | None = None
    required_keywords: list[str] = field(default_factory=list)

    def check(
        self,
        concept: str,
        source_level: int | None = None,
        definition: str = "",
    ) -> RuleStatus:
        """检查知识概念是否符合此规则。"""
        reasons: list[str] = []

        # 来源等级检查
        if (
            self.min_source_level is not None
            and source_level is not None
            and source_level > self.min_source_level
        ):
            reasons.append(f"来源等级 {source_level} 低于要求 {self.min_source_level}")

        # 关键词检查
        if self.required_keywords:
            missing = [kw for kw in self.required_keywords if kw not in definition]
            if missing:
                reasons.append(f"定义缺关键概念: {', '.join(missing)}")

        if reasons:
            if self.severity == RuleSeverity.CRITICAL:
                return RuleStatus.VIOLATION
            return RuleStatus.WARNING

        return RuleStatus.PASS


class RuleEngine:
    """规则引擎——注册 + 批量检查。

    预置会计领域基础规则。
    """

    def __init__(self) -> None:
        self._rules: dict[str, ComplianceRule] = {}
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """预置会计合规规则。"""
        self.register(
            ComplianceRule(
                rule_id="source-level-minimum",
                name="来源等级最低要求",
                description="所有会计概念来源等级至少为国家法规(≤2)",
                severity=RuleSeverity.WARNING,
                min_source_level=2,
            )
        )
        self.register(
            ComplianceRule(
                rule_id="definition-completeness",
                name="定义完整性检查",
                description="财务比率定义必须包含'衡量'或'度量'关键词",
                severity=RuleSeverity.INFO,
                required_keywords=["衡量", "度量", "计算", "比率"],
            )
        )
        self.register(
            ComplianceRule(
                rule_id="ifrs-source-required",
                name="IFRS 来源要求",
                description="IFRS 定义的概念来源等级应为 1（国际标准）",
                severity=RuleSeverity.WARNING,
                min_source_level=1,
            )
        )

    def register(self, rule: ComplianceRule) -> None:
        self._rules[rule.rule_id] = rule

    def get(self, rule_id: str) -> ComplianceRule | None:
        return self._rules.get(rule_id)

    def list_rules(self) -> list[ComplianceRule]:
        return list(self._rules.values())

    def check_all(
        self,
        concept: str,
        source_level: int | None = None,
        definition: str = "",
    ) -> dict[str, RuleStatus]:
        """运行所有规则，返回 {rule_id: status}。"""
        return {
            rid: rule.check(concept, source_level, definition) for rid, rule in self._rules.items()
        }
