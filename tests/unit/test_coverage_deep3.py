"""覆盖率深度补测——路由层基础 + 模块级纯函数 + hallucination models."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app
from orbit.hallucination.schemas import (
    HallucinationLevel,
    L3EntropyConfig,
    L6ContractMatch,
    ValidationResult,
)


# ════════════════════════════════════════════
# 1. 路由冒烟测试
# ════════════════════════════════════════════

class TestRouteSmoke:
    @pytest.fixture
    def client(self):
        app = create_app(enable_auth=False)
        return TestClient(app)

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_docs_endpoint(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_endpoint(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_metrics_endpoint(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200


# ════════════════════════════════════════════
# 2. Hallucination schemas 全部模型
# ════════════════════════════════════════════

class TestHallucinationSchemasFull:
    def test_all_levels(self):
        levels = list(HallucinationLevel)
        assert len(levels) >= 8  # L1-L8

    def test_l1_graph_level(self):
        assert HallucinationLevel.L1_GRAPH.value

    def test_l3_entropy_level(self):
        assert HallucinationLevel.L3_ENTROPY.value

    def test_l5_z3_level(self):
        assert HallucinationLevel.L5_Z3.value

    def test_l8_config_level(self):
        assert HallucinationLevel.L8_CONFIG.value

    def test_l3_entropy_config_custom(self):
        cfg = L3EntropyConfig(
            window_size=20, threshold=0.8, fallback_enabled=False,
        )
        assert cfg.window_size == 20
        assert cfg.fallback_enabled is False

    def test_l6_contract_match(self):
        m = L6ContractMatch(
            endpoint="/api/users", method="GET",
            request_model="UserRequest", response_model="UserResponse",
            matched=True,
        )
        assert m.matched is True
        assert m.endpoint == "/api/users"

    def test_validation_result_with_warnings(self):
        vr = ValidationResult(
            passed=True, level=HallucinationLevel.L2_DYNAMIC,
            warnings=["slow response"],
            metadata={"duration_ms": 500},
        )
        assert len(vr.warnings) == 1


# ════════════════════════════════════════════
# 3. Task schemas 全部模型
# ════════════════════════════════════════════

class TestTaskSchemasAll:
    def test_all_states(self):
        from orbit.api.schemas.task import TaskState
        states = list(TaskState)
        # 至少包含基本生命周期状态
        state_values = {s.value for s in states}
        assert "IDLE" in state_values
        assert "PARSING" in state_values
        assert "PLANNING" in state_values
        assert "CODING" in state_values
        assert "VERIFYING" in state_values
        assert "DONE" in state_values
        assert "FAILED" in state_values

    def test_task_create_minimal(self):
        from orbit.api.schemas.task import TaskCreateRequest
        req = TaskCreateRequest(prd="build a calculator application", language="python")
        assert req.language == "python"

    def test_task_create_with_callback(self):
        from orbit.api.schemas.task import TaskCreateRequest
        req = TaskCreateRequest(
            prd="build a test project description",
            language="javascript",
            callback_url="https://example.com/callback",
        )
        assert req.callback_url is not None
