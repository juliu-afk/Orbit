"""Step 8——元图谱单元测试。"""

import os

from orbit.graph.meta_graph import MetaGraph, RelationType


class TestMetaGraph:
    """元图谱——跨图谱关系。"""

    def test_add_and_impact_analysis(self) -> None:
        mg = MetaGraph()
        try:
            mg.add_relation(
                "code", "PaymentService.process", RelationType.WRITES_TO, "db", "payments"
            )
            mg.add_relation(
                "code", "PaymentService.process", RelationType.READS_FROM, "db", "accounts"
            )
            mg.add_relation(
                "code",
                "PaymentService.process",
                RelationType.DEPENDS_ON,
                "config",
                "PAYMENT_TIMEOUT",
            )

            impact = mg.impact_analysis("code", "PaymentService.process")
            assert "payments" in impact["databases"]
            assert "accounts" in impact["databases"]
            assert "PAYMENT_TIMEOUT" in impact["configs"]
        finally:
            mg.close()
            _cleanup()

    def test_impact_analysis_empty_for_unknown_node(self) -> None:
        mg = MetaGraph()
        try:
            impact = mg.impact_analysis("code", "NonExistent.func")
            assert impact["databases"] == []
            assert impact["configs"] == []
            assert impact["knowledge"] == []
        finally:
            mg.close()
            _cleanup()

    def test_config_impact_trace(self) -> None:
        mg = MetaGraph()
        try:
            mg.add_relation(
                "config", "PAYMENT_TIMEOUT", RelationType.DECIDED_AT, "reasoning", "task-001"
            )
            mg.add_relation(
                "config", "PAYMENT_TIMEOUT", RelationType.CONNECTS_TO, "code", "gateway.py"
            )
            trace = mg.config_impact_trace("PAYMENT_TIMEOUT")
            assert "gateway.py" in trace["affected_code"]
            assert "task-001" in trace["affected_tasks"]
        finally:
            mg.close()
            _cleanup()

    def test_architecture_health_detects_violation(self) -> None:
        mg = MetaGraph()
        try:
            # 写入数据库但无合规关联 → 腐化
            mg.add_relation("code", "badFunc", RelationType.WRITES_TO, "db", "orders")
            violations = mg.architecture_health_check()
            assert len(violations) >= 1
            assert violations[0]["source"] == "badFunc"
        finally:
            mg.close()
            _cleanup()

    def test_architecture_health_clean(self) -> None:
        mg = MetaGraph()
        try:
            mg.add_relation("code", "goodFunc", RelationType.WRITES_TO, "db", "orders")
            mg.add_relation(
                "code", "goodFunc", RelationType.COMPLIES_WITH, "knowledge", "accounting_rules"
            )
            violations = mg.architecture_health_check()
            # 有合规关联 → 无违规
            assert len(violations) == 0
        finally:
            mg.close()
            _cleanup()

    def test_count(self) -> None:
        mg = MetaGraph()
        try:
            assert mg.count() == 0
            mg.add_relation("code", "a", RelationType.CONNECTS_TO, "code", "b")
            assert mg.count() == 1
        finally:
            mg.close()
            _cleanup()

    def test_list_relations(self) -> None:
        mg = MetaGraph()
        try:
            mg.add_relation("code", "x", RelationType.READS_FROM, "db", "y")
            mg.add_relation("code", "z", RelationType.WRITES_TO, "db", "w")
            assert len(mg.list_relations()) == 2
        finally:
            mg.close()
            _cleanup()


def _cleanup() -> None:
    if os.path.exists("data/meta_graph.db"):
        os.remove("data/meta_graph.db")
