"""测试库自身测试——factories/ 模块。

验证所有工厂函数产出类型正确、字段完整、默认值合理。
"""

from __future__ import annotations

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole
from orbit.checkpoint.manager import CheckpointData
from orbit.gateway.schemas import LLMRequest, LLMResponse, LLMUsage
from orbit.stream.events import StreamEvent, StreamEventType


class TestAgentFactories:
    def test_create_agent_input_defaults(self):
        from tests.lib.factories import create_agent_input

        ai = create_agent_input()
        assert isinstance(ai, AgentInput)
        assert ai.task == "测试需求：实现用户登录功能"
        assert ai.role == AgentRole.DEVELOPER
        assert isinstance(ai.context, dict)

    def test_create_agent_input_custom(self):
        from tests.lib.factories import create_agent_input

        ai = create_agent_input(task="custom task", role="architect", context={"key": "val"})
        assert ai.task == "custom task"
        assert ai.role == AgentRole.ARCHITECT
        assert ai.context["key"] == "val"

    def test_create_agent_output_ok(self):
        from tests.lib.factories import create_agent_output

        ao = create_agent_output()
        assert isinstance(ao, AgentOutput)
        assert ao.status == "ok"
        assert ao.error is None
        assert "output" in ao.result

    def test_create_agent_output_error(self):
        from tests.lib.factories import create_agent_output

        ao = create_agent_output(status="error", error="something went wrong")
        assert ao.status == "error"
        assert ao.error == "something went wrong"


class TestLLMFactories:
    def test_create_llm_request(self):
        from tests.lib.factories import create_llm_request

        req = create_llm_request()
        assert isinstance(req, LLMRequest)
        assert req.prompt == "测试需求：实现用户登录功能"
        assert req.temperature == 0.2
        assert req.max_tokens == 2048

    def test_create_llm_request_custom(self):
        from tests.lib.factories import create_llm_request

        req = create_llm_request(prompt="hello", temperature=0.5, tools=[{"name": "read"}])
        assert req.prompt == "hello"
        assert req.temperature == 0.5
        assert req.tools == [{"name": "read"}]

    def test_create_llm_response(self):
        from tests.lib.factories import create_llm_response

        resp = create_llm_response()
        assert isinstance(resp, LLMResponse)
        assert "print" in resp.content
        assert resp.model == "deepseek/deepseek-v4-pro"
        assert resp.stop_reason == "end_turn"

    def test_create_llm_response_with_tool_calls(self):
        from tests.lib.factories import create_llm_response

        resp = create_llm_response(
            tool_calls=[{"name": "read_file", "args": {"path": "a.py"}}]
        )
        assert resp.stop_reason == "tool_calls"
        assert len(resp.tool_calls) == 1

    def test_create_llm_usage(self):
        from tests.lib.factories import create_llm_usage

        usage = create_llm_usage(prompt_tokens=50, completion_tokens=150)
        assert usage.prompt_tokens == 50
        assert usage.completion_tokens == 150
        assert usage.total_tokens == 200


class TestCheckpointFactory:
    def test_create_checkpoint(self):
        from tests.lib.factories import create_checkpoint

        ck = create_checkpoint(state="CODING")
        assert isinstance(ck, CheckpointData)
        assert ck.state == "CODING"
        assert ck.retry_count == 0
        assert 0.0 <= ck.progress <= 1.0

    def test_create_checkpoint_custom(self):
        from tests.lib.factories import create_checkpoint

        ck = create_checkpoint(task_id="t1", state="DONE", retry_count=2, progress=1.0)
        assert ck.task_id == "t1"
        assert ck.state == "DONE"
        assert ck.retry_count == 2
        assert ck.progress == 1.0


class TestEventFactories:
    def test_create_stream_event_default(self):
        from tests.lib.factories import create_stream_event

        evt = create_stream_event(event_type="text_delta")
        assert isinstance(evt, StreamEvent)
        assert evt.type == StreamEventType.TEXT_DELTA
        assert evt.agent_id == "developer"

    def test_create_text_delta(self):
        from tests.lib.factories import create_text_delta

        evt = create_text_delta(delta="hello world")
        assert evt.type == StreamEventType.TEXT_DELTA
        assert evt.data["delta"] == "hello world"

    def test_create_tool_call_event(self):
        from tests.lib.factories import create_tool_call_event

        evt = create_tool_call_event(tool="read_file", args={"path": "test.py"})
        assert evt.type == StreamEventType.TOOL_CALL
        assert evt.data["tool"] == "read_file"

    def test_create_tool_result_event(self):
        from tests.lib.factories import create_tool_result_event

        evt = create_tool_result_event(result_size=2048, truncated=True)
        assert evt.type == StreamEventType.TOOL_RESULT
        assert evt.data["result_size"] == 2048
        assert evt.data["truncated"] is True

    def test_create_finish_step(self):
        from tests.lib.factories import create_finish_step

        evt = create_finish_step(output="done", turns=5, tool_calls=3)
        assert evt.type == StreamEventType.FINISH_STEP
        assert evt.data["output"] == "done"


class TestPRDFactory:
    def test_create_prd_short(self):
        from tests.lib.factories import create_prd

        prd = create_prd("short")
        assert "POST /auth/login" in prd

    def test_create_prd_normal(self):
        from tests.lib.factories import create_prd

        prd = create_prd("normal")
        assert "验收标准" in prd

    def test_create_prd_complex(self):
        from tests.lib.factories import create_prd

        prd = create_prd("complex")
        assert "多租户" in prd


class TestTaskFactory:
    def test_create_task(self):
        from tests.lib.factories import create_task

        task = create_task()
        assert "id" in task
        assert task["agent_role"] == "developer"
        assert task["depends_on"] == []

    def test_create_task_graph(self):
        from tests.lib.factories import create_task_graph

        tasks = create_task_graph(3)
        assert len(tasks) == 3
        assert "task_1" in tasks
        assert tasks["task_1"]["depends_on"] == []

    def test_create_task_graph_with_deps(self):
        from tests.lib.factories import create_task_graph_with_deps

        tasks = create_task_graph_with_deps({2: [1], 3: [1]})
        assert len(tasks) == 3
        assert "task_1" in tasks["task_2"]["depends_on"]


class TestGraphFactory:
    def test_create_graph_node(self):
        from tests.lib.factories import create_graph_node

        node = create_graph_node()
        assert node["status"] == "PENDING"
        assert node["agent_role"] == "developer"

    def test_create_dag_layers(self):
        from tests.lib.factories import create_dag_layers

        layers = [["parse"], ["design_a", "design_b"], ["implement"]]
        nodes = create_dag_layers(layers)
        assert len(nodes) == 4
        # 第二层节点依赖第一层
        assert nodes[1]["depends_on"] == ["node_0_0"]


class TestSandboxFactory:
    def test_create_sandbox_result(self):
        from tests.lib.factories import create_sandbox_result

        sr = create_sandbox_result(exit_code=0, stdout="OK")
        assert sr["exit_code"] == 0
        assert sr["stdout"] == "OK"
        assert sr["duration_ms"] == 150


class TestAuditFactory:
    def test_create_audit_entry(self):
        from tests.lib.factories import create_audit_entry

        ae = create_audit_entry(event="task.state_change")
        assert ae["event"] == "task.state_change"
        assert "trace_id" in ae
        assert "timestamp" in ae

    def test_create_cost_record(self):
        from tests.lib.factories import create_cost_record

        cr = create_cost_record(model="glm-5.2")
        assert cr["model"] == "glm-5.2"
        assert cr["prompt_tokens"] + cr["completion_tokens"] == cr["total_tokens"]
