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
from orbit.api.dependencies import AuthMiddleware
from orbit.api.routes import (
    agent_llm,
    backup,
    blame_routes,
    chat,
    codegraph_routes,
    compliance,
    compliance_routes,
    compose,
    diagnostics_ws,
    dream,
    files_routes,
    git_routes,
    goal,
    health,
    insights_routes,
    knowledge,
    loop,
    observability,
    projects,
    review,
    schedule,
    search_routes,
    sessions,
    tasks,
    terminal_routes,
    tests_routes,
    versioning,
)
from orbit.checkpoint.manager import CheckpointManager
from orbit.compression.budget import TokenBudgetTracker as _BudgetTracker
from orbit.compression.compressor import ContextCompressor as _ContextCompressor
from orbit.core.config import settings
from orbit.events.bus import EventBus
from orbit.gateway.client import MODEL_FLASH, MODEL_GLM5, MODEL_PRO, LLMClient
from orbit.scheduler.orchestrator import Scheduler
from orbit.stream.sse import router as sse_router
from orbit.ws.router import router as ws_router
from orbit.ws.router import start_broadcaster

logger = structlog.get_logger("orbit.api")


def create_app(
    event_bus: EventBus | None = None,
    enable_auth: bool = True,
) -> FastAPI:
    """应用工厂。

    WHY 工厂模式而非模块级全局 app：测试时每个用例可独立配置 app，
    避免状态污染；生产部署也能按环境注入不同中间件。

    event_bus：Step 6.1 Dashboard 事件总线。测试可注入 Mock，
    生产传 EventBus() 实例。为 None 时不启动广播协程。
    enable_auth：测试可传 False 跳过鉴权中间件（默认 True）。
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.11.0",
        description="轻量级多Agent软件开发自循环系统",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # 鉴权中间件——CORS 之后注册（Starlette 中间件执行顺序：后注册的先执行）
    # WHY: Issue #126 P0-1——CORS全开+无鉴权=本地RCE攻击链
    # WHY 显式 ORBIT_AUTH_TOKEN 环境变量才启用: 向后兼容测试/开发环境
    if enable_auth and settings.AUTH_ENABLED:
        app.add_middleware(AuthMiddleware)

    # CORS——Tauri 桌面壳跨域请求后端 API
    # WHY 从settings读取而非硬编码"*": P0-1 修复——收紧跨域来源
    _origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
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
    # Phase 2: /dream 记忆合并自循环端点
    app.include_router(dream.router, prefix=settings.API_V1_STR)
    # goal/loop 路由文件已自带 /api/v1/goal 前缀，不重复加 API_V1_STR
    app.include_router(goal.router)
    app.include_router(loop.router)
    # Step 9: IDE 功能追赶——审查 + 文件 + Git
    app.include_router(review.router, prefix=settings.API_V1_STR)
    app.include_router(files_routes.router, prefix=settings.API_V1_STR)
    app.include_router(git_routes.router, prefix=settings.API_V1_STR)
    # Step 9 Phase 1.3: 代码导航 + 搜索
    app.include_router(codegraph_routes.router, prefix=settings.API_V1_STR)
    app.include_router(search_routes.router, prefix=settings.API_V1_STR)
    # Step 9 Phase 1.4: 测试结果 + 覆盖率
    app.include_router(tests_routes.router, prefix=settings.API_V1_STR)
    # Step 9 Phase 2: Git Blame
    app.include_router(blame_routes.router, prefix=settings.API_V1_STR)
    # D13: 高峰避让延迟调度
    app.include_router(schedule.router)
    # Step 9 Phase 3: 智能洞察
    app.include_router(insights_routes.router, prefix=settings.API_V1_STR)
    app.include_router(compliance_routes.router, prefix=settings.API_V1_STR)
    # Step 9 Phase 2.5: 集成终端
    app.include_router(terminal_routes.router, prefix=settings.API_V1_STR)
    # Phase 2: 实时诊断 WebSocket——不加 API_V1_STR 前缀
    app.include_router(diagnostics_ws.router)
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

    # 启动后台任务（EventBus 广播 + Actor Watchdog）
    @app.on_event("startup")
    async def _startup_background() -> None:
        if event_bus is not None:
            asyncio.create_task(start_broadcaster(event_bus))
            logger.info("ws_broadcaster_started")
        # _actor_watchdog 是模块级单例（line 168），factory 闭包可直接引用
        asyncio.create_task(_actor_watchdog.run())  # type: ignore[possibly-undefined]
        logger.info("watchdog_started")

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

# Phase 2 AC7: 上下文压缩实例
_compressor = _ContextCompressor(llm_client=_llm_flash)
_budget_tracker = _BudgetTracker()

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

# Phase 2: /dream 记忆合并引擎（无需 LLM 也能跑纯文本合并）
from orbit.dream.engine import DreamEngine  # noqa: E402
from orbit.memory.store import MemoryStore  # noqa: E402

_dream_engine = DreamEngine(memory_store=MemoryStore())

# Phase 4 AC-A4: PermissionEngine 挂载到 ToolRegistry
from orbit.tools.registry import ToolRegistry  # noqa: E402

ToolRegistry.get_instance().set_permission(_permission_engine)

_checkpoint_manager = CheckpointManager(redis_client=_redis_client)
_scheduler = Scheduler(
    agent_llms=_agent_llms,
    event_bus=_event_bus,
    agent_factory=AgentFactory,
    checkpoint_manager=_checkpoint_manager,
    compressor=_compressor,  # Phase 2 AC7
    budget_tracker=_budget_tracker,  # Phase 2 AC7
)
# Phase 4: 注入 Compose + ActorSpawn
_scheduler._compose_orchestrator = _compose_orchestrator  # type: ignore[attr-defined]

# Step 9: 审查模块——SQLAlchemy 2.0 ORM
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from orbit.files.service import FileService  # noqa: E402
from orbit.review.models import ReviewBase  # noqa: E402
from orbit.review.service import ReviewService  # noqa: E402

_review_engine = create_async_engine(settings.DATABASE_URL, echo=False)
_review_session_factory = async_sessionmaker(_review_engine, expire_on_commit=False)
_review_service = ReviewService(_review_session_factory)
_ws_dir = settings.WORKSPACE_DIR or os.getcwd()  # P0-7: 优先使用配置
_file_service = FileService(_ws_dir)

review.set_review_service(_review_service)
files_routes.set_file_service(_file_service)
git_routes.set_workspace_dir(_ws_dir)
# Step 9 Phase 1.3: CodeGraph 引擎——复用 graph 数据库连接
from orbit.graph.engines.code_graph import CodeGraphEngine  # noqa: E402

_code_graph_engine = CodeGraphEngine(_review_session_factory)

codegraph_routes.set_code_graph(_code_graph_engine)
codegraph_routes.set_file_service(_file_service)
insights_routes.set_code_graph(_code_graph_engine)
insights_routes.set_review_service(_review_service)
compliance_routes.set_file_service(_file_service)
search_routes.set_workspace(_ws_dir)
tests_routes.set_workspace(_ws_dir)
# Step 9 Phase 2: 诊断服务
from orbit.lsp.service import DiagnosticService  # noqa: E402

_diagnostic_service = DiagnosticService(_ws_dir)

blame_routes.set_workspace(_ws_dir)
terminal_routes.set_workspace(_ws_dir)
diagnostics_ws.set_diagnostic_service(_diagnostic_service)

app = create_app(_event_bus)


@app.on_event("startup")
async def _init_review_tables() -> None:
    async with _review_engine.begin() as conn:
        await conn.run_sync(ReviewBase.metadata.create_all)


@app.on_event("shutdown")
async def _shutdown_review() -> None:
    await _review_engine.dispose()  # P0-8: 释放连接池


# Phase 4: 注入 ComposeOrchestrator 到 app state（供 API 端点访问）
app.state.compose_orchestrator = _compose_orchestrator
app.state.dream_engine = _dream_engine

# Goal+Loop: 注入 MetaOrchestrator + LoopScheduler + CritiqueAgent + ModelEnsemble
from orbit.goal.compose_bridge import GoalComposeBridge  # noqa: E402
from orbit.goal.critique import CritiqueAgent  # noqa: E402
from orbit.goal.ensemble import ModelEnsemble  # noqa: E402
from orbit.goal.meta_orchestrator import MetaOrchestrator  # noqa: E402
from orbit.loop.scheduler import LoopScheduler  # noqa: E402

_critique_agent = CritiqueAgent(llm=_llm_flash, model_family="anthropic")
_model_ensemble = ModelEnsemble(
    agent_factory=AgentFactory, judge_llm=_llm_flash, ensemble_models=["claude-opus", "gpt-4o"]
)
_meta_orchestrator = MetaOrchestrator(
    compose_bridge=GoalComposeBridge(llm=_llm_flash),
    critique_agent=_critique_agent,
    ensemble=_model_ensemble,
    compose_orchestrator=_compose_orchestrator,
    agent_factory=AgentFactory,
    max_parallel_tasks=5,
)
_loop_scheduler = LoopScheduler(command_executor=_meta_orchestrator.run)
app.state.meta_orchestrator = _meta_orchestrator
app.state.loop_scheduler = _loop_scheduler

# D13: 高峰避让延迟调度器——延迟初始化，避免 import 时创建 SQLite/YAML
app.state.offpeak_scheduler = None
app.state.peak_window_manager = None

if settings.OFFPEAK_ENABLED:
    from orbit.goal.preflight import PreFlightEstimator  # noqa: E402
    from orbit.scheduler.offpeak_scheduler import (  # noqa: E402
        DeferredQueue,
        OffPeakScheduler,
        PeakWindowManager,
    )

    async def _init_offpeak() -> None:
        _peak_manager = PeakWindowManager(config_path=settings.OFFPEAK_CONFIG_PATH)
        _offpeak_queue = DeferredQueue(db_path=settings.OFFPEAK_DB_PATH)
        _offpeak_scheduler = OffPeakScheduler(
            peak_manager=_peak_manager,
            queue=_offpeak_queue,
            orchestrator=_meta_orchestrator,
            preflight=PreFlightEstimator(),
        )
        await _offpeak_scheduler.start()
        app.state.offpeak_scheduler = _offpeak_scheduler
        app.state.peak_window_manager = _peak_manager
        logger.info("offpeak_scheduler_initialized", config_path=settings.OFFPEAK_CONFIG_PATH)

    app.add_event_handler("startup", _init_offpeak)
