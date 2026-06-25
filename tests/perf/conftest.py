"""性能测试 fixtures——独立于 E2E conftest。

WHY 独立：pytest 的 conftest 按目录层级发现，tests/perf/ 是 tests/e2e/ 的兄弟，
不共享 fixture。性能测试用独立的轻量 app，避免跨目录依赖。
"""

from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from orbit.api.main import create_app
from orbit.checkpoint.manager import CheckpointManager
from orbit.events.bus import EventBus
from orbit.sandbox.sandbox_factory import create_sandbox
from orbit.scheduler.orchestrator import Scheduler
from tests.e2e.mock_llm import MockLLMClient


@pytest_asyncio.fixture(scope="session")
async def e2e_app() -> Any:
    """独立 perf app——与 E2E 相同的堆栈但独立实例。"""
    bus = EventBus()
    llm = MockLLMClient(fail_count=0, fixed_response="[mock] PERF OK")
    _ = await create_sandbox()
    cp = CheckpointManager()
    scheduler = Scheduler(agent_llms=None, checkpoint_manager=cp, event_bus=bus)
    app = create_app(event_bus=bus)
    app.state.scheduler = scheduler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client._scheduler = scheduler  # type: ignore[attr-defined]
        client._app = app  # type: ignore[attr-defined]
        yield client
