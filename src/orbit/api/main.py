"""FastAPI 应用入口（Step 1.1 + Step 6.1 WS 扩展 + Step 7.1 Prometheus）。

WHY 分层：main 只负责组装 app（路由注册、中间件、异常处理），
不写业务逻辑。路由在 routes/，模型在 schemas/，配置在 core/。
"""

from __future__ import annotations

import asyncio
import os

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from orbit.agents.factory import AgentFactory
from orbit.api.routes import (
    agent_llm,
    backup,
    chat,
    compliance,
    compose,
    health,
    knowledge,
    observability,
    projects,
    sessions,
    tasks,
    versioning,
)
from orbit.checkpoint.manager import CheckpointManager
from orbit.core.config import settings
from orbit.events.bus import EventBus
from orbit.gateway.client import MODEL_FLASH, MODEL_GLM5, MODEL_PRO, LLMClient
from orbit.scheduler.orchestrator import Scheduler
from orbit.stream.sse import router as sse_router
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
    # CORS——data: URI boot.html 跨域请求后端 API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
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
    app.include_router(backup.router, prefix=settings.API_V1_STR)
    app.include_router(versioning.router, prefix=settings.API_V1_STR)
    app.include_router(chat.router, prefix=settings.API_V1_STR)
    # Session + Project API（Session PR #1）
    app.include_router(sessions.router, prefix=settings.API_V1_STR)
    app.include_router(projects.router, prefix=settings.API_V1_STR)
    # Agent LLM 配置 API（Step 2.3 智能路由）
    app.include_router(agent_llm.router, prefix=settings.API_V1_STR)
    # Phase 4 AC-A7: Compose 编排端点
    app.include_router(compose.router, prefix=settings.API_V1_STR)
    # /health 不加 API_V1_STR 前缀——符合 K8s 探针惯例
    app.include_router(health.router)
    # Phase 4 AC-A1: SSE 流式端点
    app.include_router(sse_router)
    # WebSocket 路由（Step 6.1 驾驶舱）
    app.include_router(ws_router)

    # Prometheus 指标（Step 7.1 生产部署）
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # 前端静态文件 (PyInstaller 打包时 static/ 在 sys._MEIPASS 下)
    import sys

    # WHY backend/static/：源代码目录结构要加 backend/ 前缀，
    # PyInstaller 打包时 datas 映射 backend/static → static/
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend", "static")
    if getattr(sys, "frozen", False):
        static_dir = os.path.join(sys._MEIPASS, "static")  # type: ignore[attr-defined]
    if os.path.isdir(static_dir):
        app.mount(
            "/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets"
        )
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    # 启动 EventBus→WS 广播协程
    if event_bus is not None:

        @app.on_event("startup")
        async def _start_broadcaster() -> None:
            asyncio.create_task(start_broadcaster(event_bus))
            logger.info("ws_broadcaster_started")

    # ClarifierAgent 用 Flash 轻量模型
    from orbit.gateway.client import LLMClient as _LLMClient

    chat.set_clarifier_llm(_LLMClient(default_model=MODEL_FLASH))

    return app


_event_bus = EventBus()
try:
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=False,
        max_connections=16,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
except Exception:
    logger.warning("redis_init_failed_fallback_memory")
    _redis_client = None

# ── 按角色创建 LLMClient，每个 Agent 用其配置的模型 ──
_llm_pro = LLMClient(default_model=MODEL_PRO)
_llm_flash = LLMClient(default_model=MODEL_FLASH)
_llm_glm5 = LLMClient(default_model=MODEL_GLM5)

# Tier 分配: Flash(T1)=轻量, Pro(T2)=中档, GLM-5.2(T3)=最强
# developer 默认 T2, 失败时升级链: T1→T2→T3
_agent_llms: dict[str, LLMClient] = {
    "architect": _llm_glm5,  # T3 GLM-5.2——架构需要最强推理
    "developer": _llm_pro,  # T2 DS V4 Pro——编码中档起步, 失败升T3
    "reviewer": _llm_pro,  # T2 DS V4 Pro——审查中档够用
    "qa": _llm_pro,  # T2 DS V4 Pro——测试中档够用
    "config_manager": _llm_flash,  # T1 DS Flash——配置轻量即可
    "clarifier": _llm_flash,  # T1 DS Flash——对话轻量即可
}

# ── Phase 4 AC-A2: Actor 子系统实例 ──
from orbit.actors.registry import ActorRegistry  # noqa: E402
from orbit.actors.spawn import ActorSpawn  # noqa: E402
from orbit.actors.watchdog import ActorWatchdog  # noqa: E402
from orbit.compose.orchestrator import ComposeOrchestrator  # noqa: E402
from orbit.security.permission import PermissionEngine  # noqa: E402

_actor_registry = ActorRegistry()
_actor_spawn = ActorSpawn(registry=_actor_registry, agent_factory=AgentFactory)
_compose_orchestrator = ComposeOrchestrator(actor_spawn=_actor_spawn)
_permission_engine = PermissionEngine()
_actor_watchdog = ActorWatchdog(_actor_registry)

# Phase 4 AC-A4: PermissionEngine 挂载到 ToolRegistry
from orbit.tools.registry import ToolRegistry  # noqa: E402

ToolRegistry.get_instance().set_permission(_permission_engine)

_checkpoint_manager = CheckpointManager(redis_client=_redis_client)
_scheduler = Scheduler(
    agent_llms=_agent_llms,
    event_bus=_event_bus,
    agent_factory=AgentFactory,
    checkpoint_manager=_checkpoint_manager,
)
# Phase 4: 注入 Compose + ActorSpawn
_scheduler._compose_orchestrator = _compose_orchestrator  # type: ignore[attr-defined]
app = create_app(_event_bus)

# Phase 4: 注入 ComposeOrchestrator 到 app state（供 API 端点访问）
app.state.compose_orchestrator = _compose_orchestrator


# Phase 4 AC-A3: Watchdog 在 startup 事件中启动
@app.on_event("startup")
async def _start_watchdog() -> None:
    import asyncio

    asyncio.create_task(_actor_watchdog.run())
    logger.info("watchdog_started")
