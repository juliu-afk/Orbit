"""FastAPI 应用入口（Step 1.1 + Step 6.1 WS 扩展 + Step 7.1 Prometheus）。

WHY 分层：main 只负责组装 app（路由注册、中间件、异常处理），
不写业务逻辑。路由在 routes/，模型在 schemas/，配置在 core/。
"""

from __future__ import annotations

import asyncio

import os

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from orbit.api.routes import chat, compliance, health, knowledge, observability, tasks
from orbit.core.config import settings
from orbit.events.bus import EventBus
from orbit.ws.router import router as ws_router
from orbit.ws.router import start_broadcaster

logger = structlog.get_logger()


def create_app(event_bus: EventBus | None = None) -> FastAPI:
    """应用工厂。

    WHY 工厂模式而非模块级全局 app：测试时每个用例可独立配置 app，
    避免状态污染；生产部署也能按环境注入不同中间件。

    event_bus：Step 6.1 Dashboard 事件总线。测试可注入 Mock，
    生产传 EventBus() 实例。为 None 时不启动广播协程。
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.11.0",
        description="轻量级多Agent软件开发自循环系统",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # REST 路由（Step 1.1）
    app.include_router(tasks.router, prefix=settings.API_V1_STR)
    # 知识图谱 API（Step 3.4b）
    app.include_router(knowledge.router, prefix=settings.API_V1_STR)
    # 合规验证 API（Step 4.3）
    app.include_router(compliance.router, prefix=settings.API_V1_STR)
    # 可观测性 API（Step 7.2）
    app.include_router(observability.router, prefix=settings.API_V1_STR)
    # 自然语言聊天 API（NL交互 PR #3）
    app.include_router(chat.router, prefix=settings.API_V1_STR)
    # /health 不加 API_V1_STR 前缀——符合 K8s 探针惯例
    app.include_router(health.router)
    # WebSocket 路由（Step 6.1 驾驶舱）
    app.include_router(ws_router)

    # Prometheus 指标（Step 7.1 生产部署）
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # 前端静态文件 (PyInstaller 打包时 static/ 在 sys._MEIPASS 下)
    import sys

    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "static")
    if getattr(sys, "frozen", False):
        static_dir = os.path.join(sys._MEIPASS, "static")  # type: ignore[attr-defined]
    if os.path.isdir(static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    # 启动 EventBus→WS 广播协程
    if event_bus is not None:

        @app.on_event("startup")
        async def _start_broadcaster() -> None:
            asyncio.create_task(start_broadcaster(event_bus))
            logger.info("ws_broadcaster_started")

    return app


app = create_app()
