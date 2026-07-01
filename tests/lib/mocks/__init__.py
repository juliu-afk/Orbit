"""可配置 Mock 组件——替代生产组件，注入故障/延迟/特定输出。

每个 Mock 100% 兼容被替代组件的公共接口，通过 fixture 注入，
不 monkeypatch 全局状态。均支持链式配置 + 调用追踪 + reset()。
"""

from tests.lib.mocks.llm_client import MockLLMClient
from tests.lib.mocks.sandbox import MockSandbox
from tests.lib.mocks.checkpoint import MockCheckpointManager
from tests.lib.mocks.circuit_breaker import MockCircuitBreaker
from tests.lib.mocks.knowledge import MockKnowledgeStore
from tests.lib.mocks.event_bus import MockEventBus
from tests.lib.mocks.tool_registry import MockToolRegistry

__all__ = [
    "MockLLMClient",
    "MockSandbox",
    "MockCheckpointManager",
    "MockCircuitBreaker",
    "MockKnowledgeStore",
    "MockEventBus",
    "MockToolRegistry",
]
