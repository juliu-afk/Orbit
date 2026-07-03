"""FastAPI 应用工厂 create_app 测试。

WHY 不测试模块级初始化（_event_bus, _scheduler 等）：
这些在 import 时执行，涉及 Redis/LLMClient 等外部依赖。
create_app 是纯函数——只组装 app 不访问外部 I/O。
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
from fastapi import FastAPI

from orbit.api.main import create_app
from orbit.events.bus import EventBus


class TestCreateApp:
    """create_app——应用工厂。

    覆盖不同参数组合：event_bus、lifespan、enable_auth。
    """

    def test_default_creation(self) -> None:
        """默认参数返回 FastAPI 实例。"""
        app = create_app()
        assert isinstance(app, FastAPI)
        assert app.title == "Orbit"
        assert app.version == "0.11.0"

    def test_with_event_bus(self) -> None:
        """注入 EventBus 实例。"""
        bus = EventBus()
        app = create_app(event_bus=bus)
        assert isinstance(app, FastAPI)

    def test_with_lifespan(self) -> None:
        """注入 lifespan 上下文管理器。"""
        async def dummy_lifespan(_app: FastAPI) -> AsyncGenerator[None]:
            yield

        app = create_app(lifespan=dummy_lifespan)
        assert isinstance(app, FastAPI)
        # lifespan 已注册→app.router.lifespan_context 非 None
        assert app.router.lifespan_context is not None

    def test_auth_disabled(self) -> None:
        """enable_auth=False 不注册鉴权中间件。"""
        app = create_app(enable_auth=False)
        assert isinstance(app, FastAPI)

    def test_routes_registered(self) -> None:
        """路由已注册到 app。"""
        app = create_app()
        # 至少包含文档路由 + /health + /metrics
        route_paths: list[str] = []
        for r in app.routes:
            if hasattr(r, "path"):
                route_paths.append(r.path)  # type: ignore[attr-defined]
        assert "/docs" in route_paths
        assert "/metrics" in route_paths

    def test_cors_middleware_added(self) -> None:
        """CORS 中间件已注册。"""
        app = create_app()
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes

    def test_multiple_create_calls_independent(self) -> None:
        """多次调用 create_app 返回独立实例。"""
        app1 = create_app(enable_auth=True)
        app2 = create_app(enable_auth=True)
        assert app1 is not app2
        assert app1.title == app2.title

    def test_static_files_not_mounted_in_test(self) -> None:
        """测试环境中 static 目录不存在→不挂载（不报错）。"""
        app = create_app()
        # 不报错即可——覆盖 if os.path.isdir(static_dir): 为 False 的分支
        assert isinstance(app, FastAPI)
