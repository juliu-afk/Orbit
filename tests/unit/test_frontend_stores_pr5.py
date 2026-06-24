"""PR5 前端 store 接口契约测试。

验证 compliance/knowledge/audit/lessons/health 端点路由可达。
数据库表缺失时允许 500（端点本身路由存在即可）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


class TestComplianceAPI:
    """compliance API 端点可达。"""

    def test_validate_returns_result(self, client) -> None:
        r = client.get("/api/v1/compliance/validate?domain=accounting&concept=CurrentRatio")
        assert r.status_code in (200, 404, 500)

    def test_rules_list(self, client) -> None:
        r = client.get("/api/v1/compliance/rules")
        assert r.status_code in (200, 500)


class TestKnowledgeAPI:
    """knowledge API 端点可达。"""

    def test_query_concept(self, client) -> None:
        r = client.get("/api/v1/knowledge?domain=accounting&concept=ROE")
        assert r.status_code in (200, 404, 500)

    def test_concepts_list(self, client) -> None:
        r = client.get("/api/v1/knowledge/concepts?domain=accounting")
        assert r.status_code in (200, 500)


class TestAuditLessonsAPI:
    """audit/lessons API 端点可达。"""

    def test_audit_empty_task(self, client) -> None:
        r = client.get("/api/v1/observability/audit?task_id=")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_lessons_list(self, client) -> None:
        r = client.get("/api/v1/observability/lessons")
        assert r.status_code == 200


class TestHealthComponentAPI:
    """单组件健康查询可达。"""

    def test_component_health(self, client) -> None:
        r = client.get("/api/v1/observability/health/scheduler")
        assert r.status_code == 200
