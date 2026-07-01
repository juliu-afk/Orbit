"""Scenario 共享 fixture。

所有场景测试共用一套默认 Mock，function scope 确保隔离。
"""

from __future__ import annotations

import pytest

from tests.lib.mocks import (
    MockCheckpointManager,
    MockCircuitBreaker,
    MockEventBus,
    MockKnowledgeStore,
    MockLLMClient,
    MockSandbox,
    MockToolRegistry,
)


@pytest.fixture
def scenario_mocks() -> dict:
    """返回所有 Scenario 共用的默认 Mock 集合。

    function scope——每个测试自动重建，确保隔离。
    """
    return {
        "llm": MockLLMClient(),
        "sandbox": MockSandbox(),
        "checkpoint": MockCheckpointManager(),
        "circuit_breaker": MockCircuitBreaker(),
        "knowledge": MockKnowledgeStore(),
        "event_bus": MockEventBus(),
        "tool_registry": MockToolRegistry(),
    }
