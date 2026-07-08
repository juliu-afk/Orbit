"""causal API 路由集成测试 (FastAPI TestClient)."""

import pytest
from fastapi.testclient import TestClient


# 不依赖 dowhy 和完整 app——仅测试路由结构
class TestCausalRoutesStructure:
    """路由注册 + 输入验证."""

    def test_import_router(self):
        from orbit.api.routes.causal_routes import router
        assert router is not None
        assert router.prefix == "/api/v1/causal"

    def test_pydantic_models(self):
        from orbit.api.routes.causal_routes import (
            LearnRequest, RootCauseRequest, LearnResponse, RootCauseResponse,
        )
        # LearnRequest 默认值
        req = LearnRequest()
        assert req.min_samples == 50

        # 验证范围
        req2 = LearnRequest(min_samples=10)
        assert req2.min_samples == 10

        # RootCauseRequest 需要 task_id
        with pytest.raises(Exception):
            RootCauseRequest()  # task_id 必填

        req3 = RootCauseRequest(task_id="task-123")
        assert req3.task_id == "task-123"

    def test_setup_check_503(self):
        """未初始化 setup_causal 时端点应返回 503."""
        from orbit.api.routes.causal_routes import (
            router, _causal_manager, _root_cause_analyzer, _causal_recommender,
        )
        # 确保状态干净（如果之前的测试设置了全局变量）
        import orbit.api.routes.causal_routes as cr
        cr._causal_manager = None
        cr._root_cause_analyzer = None
        cr._causal_recommender = None

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # 所有端点都应该返回 503
        r = client.post("/api/v1/causal/learn", json={"min_samples": 50})
        assert r.status_code == 503

        r = client.post("/api/v1/causal/root-cause", json={"task_id": "test"})
        assert r.status_code == 503

        r = client.get("/api/v1/causal/graph")
        assert r.status_code == 503
