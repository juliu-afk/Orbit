"""FastAPI 应用入口（Step 1.1）。

WHY 分层：main 只负责组装 app（路由注册、中间件、异常处理），
不写业务逻辑。路由在 routes/，模型在 schemas/，配置在 core/。
"""

from __future__ import annotations

from fastapi import FastAPI

from orbit.api.routes import health, tasks
from orbit.core.config import settings


def create_app() -> FastAPI:
    """应用工厂。

    WHY 工厂模式而非模块级全局 app：测试时每个用例可独立配置 app，
    避免状态污染；生产部署也能按环境注入不同中间件。
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="轻量级多Agent软件开发自循环系统",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # 路由统一挂 API 前缀（Step 1.1 ADR：API_V1_STR=/api/v1）
    app.include_router(tasks.router, prefix=settings.API_V1_STR)
    # WHY /health 不加 API_V1_STR 前缀：符合 K8s liveness/readiness 探针惯例，
    # 探针不带版本号，避免升级时探针配置频繁改动。
    app.include_router(health.router)
    return app


app = create_app()
