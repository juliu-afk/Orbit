"""Step 4.3 合规验证器。

集成 KnowledgeStore + RuleEngine，对知识概念执行合规检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from orbit.compliance.rule_engine import RuleEngine, RuleStatus
from orbit.knowledge.store import KnowledgeStore

logger = structlog.get_logger()


@dataclass
class ComplianceResult:
    """合规检查结果。"""

    concept: str
    domain: str
    passed: bool
    status: str  # "pass" | "warning" | "violation"
    rules: dict[str, str]  # {rule_id: status}
    details: list[str] = field(default_factory=list)
    source_uri: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "domain": self.domain,
            "passed": self.passed,
            "status": self.status,
            "rules": self.rules,
            "details": self.details,
            "source_uri": self.source_uri,
        }


class ComplianceValidator:
    """合规验证器——知识概念 + 规则引擎。

    降级策略：RuleEngine 纯内存计算，无外部依赖，不会不可用。
    """

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        engine: RuleEngine | None = None,
    ) -> None:
        self._store = store or KnowledgeStore()
        # WHY 无条件 initialize：_get_conn() 已自动建表，initialize()
        # 负责种子数据导入。INSERT OR IGNORE 保证幂等，重复调用无害。
        self._store.initialize()
        self._engine = engine or RuleEngine()

    def validate(self, domain: str, concept: str) -> ComplianceResult | None:
        """验证单个知识概念的合规性。

        Returns:
            ComplianceResult 或 None（概念不存在）
        """
        row = self._store.query_exact(domain, concept)
        if row is None:
            return None

        # 运行规则引擎
        rule_results = self._engine.check_all(
            concept=concept,
            source_level=row.get("source_level"),
            definition=row.get("definition", ""),
        )

        # 汇总状态
        statuses = list(rule_results.values())
        if any(s == RuleStatus.VIOLATION for s in statuses):
            overall = "violation"
        elif any(s == RuleStatus.WARNING for s in statuses):
            overall = "warning"
        else:
            overall = "pass"

        # 生成详情
        details: list[str] = []
        for rid, status in rule_results.items():
            if status != RuleStatus.PASS:
                rule = self._engine.get(rid)
                if rule:
                    details.append(f"[{rule.severity.value}] {rule.name}: {rule.description}")

        return ComplianceResult(
            concept=concept,
            domain=domain,
            passed=overall != "violation",
            status=overall,
            rules={k: v.value for k, v in rule_results.items()},
            details=details,
            source_uri=row.get("source_uri", ""),
        )

    def validate_all(self, domain: str) -> list[ComplianceResult]:
        """验证某领域所有概念的合规性。"""
        results: list[ComplianceResult] = []
        for c in self._store.list_by_domain(domain):
            result = self.validate(domain, c["concept"])
            if result is not None:
                results.append(result)
        return results

    def list_rules(self) -> list[dict[str, Any]]:
        """列出所有合规规则。"""
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "severity": r.severity.value,
                "description": r.description,
            }
            for r in self._engine.list_rules()
        ]
