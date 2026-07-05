"""TaskModelRouter 单元测试——按任务类型自动选择模型（Inkeep 借鉴 #1）。

覆盖: reasoning/structured_output/summarization 三种路由 + 未知类型回退 + 自定义映射。
"""

from __future__ import annotations


class TestTaskTypeEnum:
    """TaskType 枚举定义。"""

    def test_all_task_types_defined(self):
        from orbit.gateway.task_router import TaskType

        assert TaskType.REASONING == "reasoning"
        assert TaskType.STRUCTURED_OUTPUT == "structured_output"
        assert TaskType.SUMMARIZATION == "summarization"

    def test_task_type_from_string(self):
        from orbit.gateway.task_router import TaskType

        assert TaskType("reasoning") == TaskType.REASONING
        assert TaskType("structured_output") == TaskType.STRUCTURED_OUTPUT


class TestTaskModelRouter:
    """TaskModelRouter——按 task_type 选模型。"""

    def test_reasoning_routes_to_pro(self):
        from orbit.gateway.task_router import TaskModelRouter, TaskType

        router = TaskModelRouter()
        decision = router.select(TaskType.REASONING)
        assert decision.model == "deepseek/deepseek-v4-pro"
        assert decision.task_type == TaskType.REASONING
        assert "task_type_match" in decision.reason

    def test_structured_output_routes_to_flash(self):
        from orbit.gateway.task_router import TaskModelRouter, TaskType

        router = TaskModelRouter()
        decision = router.select(TaskType.STRUCTURED_OUTPUT)
        assert decision.model == "deepseek/deepseek-v4-flash"
        assert decision.task_type == TaskType.STRUCTURED_OUTPUT

    def test_summarization_routes_to_glm_fallback(self):
        from orbit.gateway.task_router import TaskModelRouter, TaskType

        router = TaskModelRouter()
        decision = router.select(TaskType.SUMMARIZATION)
        # 摘要用最便宜模型
        assert decision.model == "openai/glm-4.7-flash"
        assert decision.task_type == TaskType.SUMMARIZATION

    def test_unknown_task_type_fallback_to_pro(self):
        from orbit.gateway.task_router import TaskModelRouter

        router = TaskModelRouter()
        decision = router.select("nonexistent_type")
        # 未知类型回退 Pro
        assert decision.model == "deepseek/deepseek-v4-pro"
        assert "fallback" in decision.reason

    def test_custom_mapping(self):
        from orbit.gateway.task_router import TaskModelRouter, TaskType

        router = TaskModelRouter(model_map={
            "reasoning": "openai/glm-5.2",
            "structured_output": "openai/glm-4.7-flash",
            "summarization": "openai/glm-4.7-flash",
        })
        assert router.select(TaskType.REASONING).model == "openai/glm-5.2"

    def test_update_mapping_runtime(self):
        from orbit.gateway.task_router import TaskModelRouter, TaskType

        router = TaskModelRouter()
        router.update_mapping("reasoning", "openai/glm-5.2")
        assert router.select(TaskType.REASONING).model == "openai/glm-5.2"

    def test_current_mapping_property(self):
        from orbit.gateway.task_router import TaskModelRouter

        router = TaskModelRouter()
        mapping = router.current_mapping
        assert "reasoning" in mapping
        assert "structured_output" in mapping
        assert "summarization" in mapping

    def test_decision_serializable(self):
        from orbit.gateway.task_router import TaskModelDecision, TaskType

        d = TaskModelDecision(
            task_type=TaskType.REASONING,
            model="deepseek/deepseek-v4-pro",
            reason="task_type_match_reasoning",
        )
        dumped = d.model_dump()
        assert dumped["task_type"] == "reasoning"
        assert dumped["model"] == "deepseek/deepseek-v4-pro"


class TestTaskModelRouterIntegration:
    """TaskModelRouter 与 LLMClient 集成——端到端验证 task_type 路由。"""

    def test_llm_request_has_task_type_field(self):
        from orbit.gateway.schemas import LLMRequest

        req = LLMRequest(prompt="test", task_type="reasoning")
        assert req.task_type == "reasoning"

        req_no_type = LLMRequest(prompt="test")
        assert req_no_type.task_type is None

    def test_task_type_in_task_runner_map(self):
        """验证 TaskState → task_type 映射完整性。"""
        from orbit.api.schemas.task import TaskState
        from orbit.scheduler.task_runner import _TASK_TYPE_MAP

        # 所有非终态都有映射
        for state in [TaskState.IDLE, TaskState.PARSING, TaskState.PLANNING,
                      TaskState.CODING, TaskState.VERIFYING]:
            assert state in _TASK_TYPE_MAP, f"State {state} missing task_type mapping"
            assert _TASK_TYPE_MAP[state] in ("reasoning", "structured_output", "summarization")
