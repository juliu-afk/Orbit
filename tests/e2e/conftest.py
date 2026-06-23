"""E2E 测试 fixtures。

session scope——所有 E2E 测试共享同一 app 实例，加速执行。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from orbit.api.main import create_app
from orbit.checkpoint.manager import CheckpointManager
from orbit.events.bus import EventBus
from orbit.sandbox.sandbox_factory import create_sandbox
from orbit.scheduler.orchestrator import Scheduler
from tests.e2e.mock_llm import MockLLMClient


def _docker_compose_up() -> bool:
    """启动 docker-compose.test.yml，返回是否成功。"""
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.test.yml"
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return True
    except Exception:
        return False


def _docker_compose_down() -> None:
    """停止 docker-compose.test.yml。"""
    import contextlib
    compose_file = Path(__file__).parent.parent.parent / "docker-compose.test.yml"
    with contextlib.suppress(Exception):
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down", "-v"],
            capture_output=True,
            timeout=15,
        )


@pytest.fixture(scope="session")
def docker_available() -> bool:
    """检测 Docker Engine 是否可用。

    不可用时 PG/Redis 走 SQLite fallback，不影响 E2E 执行。
    """
    if os.environ.get("CI"):
        # GitHub Actions 提供 Docker
        return True
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def use_docker(docker_available: bool) -> bool:
    """是否使用 Docker 基础设施（PG+Redis 容器）。"""
    return docker_available and _docker_compose_up()


@pytest_asyncio.fixture(scope="session")
async def e2e_app(use_docker: bool):
    """启动 E2E 应用——真实 scheduler + mock LLM + 真实沙箱。

    WHY session scope：5 个 E2E 场景共享 app，避免重复启动。
    """
    # 数据库 URL（Step 6.3 接入真实 PG/Redis 时启用）
    # if use_docker:
    #     db_url = "postgresql://test:test@localhost:5433/orbit_test"
    #     redis_url = "redis://localhost:6380/0"
    # else:
    #     db_url = f"sqlite:///{Path(__file__).parent / 'test.db'}"
    #     redis_url = None

    # 组装组件
    bus = EventBus()
    llm = MockLLMClient(fail_count=0, fixed_response="[mock] E2E OK")
    _ = await create_sandbox()  # 验证沙箱可用（不抛异常 = 可用）
    cp = CheckpointManager()
    scheduler = Scheduler(llm_client=llm, checkpoint_manager=cp, event_bus=bus)
    app = create_app(event_bus=bus)
    app.state.scheduler = scheduler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 注入 scheduler 引用供 E2E 测试使用
        client._scheduler = scheduler
        yield client

    # teardown
    if use_docker:
        _docker_compose_down()
    else:
        db_file = Path(__file__).parent / "test.db"
        db_file.unlink(missing_ok=True)


@pytest.fixture
def mock_llm():
    """每次测试独立 MockLLM——避免 call_count 跨测试污染。"""
    return MockLLMClient(fail_count=0)
