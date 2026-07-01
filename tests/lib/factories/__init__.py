"""模型工厂——一行代码创建有效测试实例。

每个工厂函数返回生产代码中的 Pydantic 模型或 dataclass 实例。
所有必填字段有合理默认值，支持 **kwargs 覆盖。
"""

from tests.lib.factories.agent import create_agent_input, create_agent_output
from tests.lib.factories.audit import create_audit_entry, create_cost_record
from tests.lib.factories.checkpoint import create_checkpoint
from tests.lib.factories.events import (
    create_finish_step,
    create_stream_event,
    create_text_delta,
    create_tool_call_event,
    create_tool_result_event,
)
from tests.lib.factories.graph import create_dag_layers, create_graph_node
from tests.lib.factories.llm import (
    create_llm_request,
    create_llm_response,
    create_llm_usage,
)
from tests.lib.factories.prd import create_prd
from tests.lib.factories.sandbox import create_sandbox_result
from tests.lib.factories.task import create_task, create_task_graph, create_task_graph_with_deps

__all__ = [
    # Agent
    "create_agent_input",
    "create_agent_output",
    # Audit
    "create_audit_entry",
    "create_cost_record",
    # Checkpoint
    "create_checkpoint",
    # Events
    "create_stream_event",
    "create_text_delta",
    "create_tool_call_event",
    "create_tool_result_event",
    "create_finish_step",
    # Graph
    "create_graph_node",
    "create_dag_layers",
    # LLM
    "create_llm_request",
    "create_llm_response",
    "create_llm_usage",
    # PRD
    "create_prd",
    # Sandbox
    "create_sandbox_result",
    # Task
    "create_task",
    "create_task_graph",
    "create_task_graph_with_deps",
]
