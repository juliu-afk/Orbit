"""FastAPI 应用入口（Step 1.1 + Step 6.1 WS 扩展 + Step 7.1 Prometheus）。

WHY 分层：main 只负责组装 app（路由注册、中间件、异常处理），
不写业务逻辑。路由在 routes/，模型在 schemas/，配置在 core/。
"""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
from pathlib import Path

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from orbit.agents.factory import AgentFactory
from orbit.api.dependencies import AuthMiddleware

# 路由模块懒加载——create_app() 内部按需导入，避免测试时全量加载 26 个路由模块
# _ROUTE_IMPORTS 映射: route_name -> (module_import_path, router_attr)
_ROUTE_MODULES: dict[str, tuple[str, str]] = {
    "tasks": ("orbit.api.routes.tasks", "router"),
    "knowledge": ("orbit.api.routes.knowledge", "router"),
    "compliance": ("orbit.api.routes.compliance", "router"),
    "observability": ("orbit.api.routes.observability", "router"),
    "backup": ("orbit.api.routes.backup", "router"),
    "versioning": ("orbit.api.routes.versioning", "router"),
    "chat": ("orbit.api.routes.chat", "router"),
    "sessions": ("orbit.api.routes.sessions", "router"),
    "projects": ("orbit.api.routes.projects", "router"),
    "agent_llm": ("orbit.api.routes.agent_llm", "router"),
    "compose": ("orbit.api.routes.compose", "router"),
    "dream": ("orbit.api.routes.dream", "router"),
    "goal": ("orbit.api.routes.goal", "router"),
    "loop": ("orbit.api.routes.loop", "router"),
    "review": ("orbit.api.routes.review", "router"),
    "files_routes": ("orbit.api.routes.files_routes", "router"),
    "git_routes": ("orbit.api.routes.git_routes", "router"),
    "codegraph_routes": ("orbit.api.routes.codegraph_routes", "router"),
    "search_routes": ("orbit.api.routes.search_routes", "router"),
    "tests_routes": ("orbit.api.routes.tests_routes", "router"),
    "blame_routes": ("orbit.api.routes.blame_routes", "router"),
    "schedule": ("orbit.api.routes.schedule", "router"),
    "insights_routes": ("orbit.api.routes.insights_routes", "router"),
    "compliance_routes": ("orbit.api.routes.compliance_routes", "router"),
    "terminal_routes": ("orbit.api.routes.terminal_routes", "router"),
    "diagnostics_ws": ("orbit.api.routes.diagnostics_ws", "router"),
    "health": ("orbit.api.routes.health", "router"),
}

# 路由懒加载映射——create_app(routes=[...]) 按需导入
# None = all routes (production), list = subset (testing)
_ROUTE_SPEC: dict[str, tuple[str, str, str | None]] = {
    "tasks":            ("orbit.api.routes.tasks", "router", "API_V1_STR"),
    "knowledge":        ("orbit.api.routes.knowledge", "router", "API_V1_STR"),
    "compliance":       ("orbit.api.routes.compliance", "router", "API_V1_STR"),
    "observability":    ("orbit.api.routes.observability", "router", "API_V1_STR"),
    "backup":           ("orbit.api.routes.backup", "router", "API_V1_STR"),
    "versioning":       ("orbit.api.routes.versioning", "router", "API_V1_STR"),
    "chat":             ("orbit.api.routes.chat", "router", "API_V1_STR"),
    "sessions":         ("orbit.api.routes.sessions", "router", "API_V1_STR"),
    "projects":         ("orbit.api.routes.projects", "router", "API_V1_STR"),
    "agent_llm":        ("orbit.api.routes.agent_llm", "router", "API_V1_STR"),
    "compose":          ("orbit.api.routes.compose", "router", "API_V1_STR"),
    "dream":            ("orbit.api.routes.dream", "router", "API_V1_STR"),
    "goal":             ("orbit.api.routes.goal", "router", None),
    "loop":             ("orbit.api.routes.loop", "router", None),
    "review":           ("orbit.api.routes.review", "router", "API_V1_STR"),
    "files_routes":     ("orbit.api.routes.files_routes", "router", "API_V1_STR"),
    "git_routes":       ("orbit.api.routes.git_routes", "router", "API_V1_STR"),
    "codegraph_routes": ("orbit.api.routes.codegraph_routes", "router", "API_V1_STR"),
    "search_routes":    ("orbit.api.routes.search_routes", "router", "API_V1_STR"),
    "tests_routes":     ("orbit.api.routes.tests_routes", "router", "API_V1_STR"),
    "blame_routes":     ("orbit.api.routes.blame_routes", "router", "API_V1_STR"),
    "schedule":         ("orbit.api.routes.schedule", "router", None),
    "insights_routes":  ("orbit.api.routes.insights_routes", "router", "API_V1_STR"),
    "compliance_routes":("orbit.api.routes.compliance_routes", "router", "API_V1_STR"),
    "terminal_routes":  ("orbit.api.routes.terminal_routes", "router", "API_V1_STR"),
    "diagnostics_ws":   ("orbit.api.routes.diagnostics_ws", "router", None),
    "health":           ("orbit.api.routes.health", "router", None),
}


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


def _lazy_import(route_name: str):
    """Lazy import a single route module. Returns (router, prefix_or_none)."""
    import importlib
    module_path, attr, prefix_flag = _ROUTE_SPEC[route_name]
    mod = importlib.import_module(module_path)
    router = getattr(mod, attr)
    prefix = settings.API_V1_STR if prefix_flag == "API_V1_STR" else ""
    return router, prefix


def create_app(
    event_bus: EventBus | None = None,
    enable_auth: bool = True,
    lifespan: object = None,
    routes: list[str] | None = None,
) -> FastAPI:
    """应用工厂。

    WHY 工厂模式而非模块级全局 app：测试时每个用例可独立配置 app，
    避免状态污染；生产部署也能按环境注入不同中间件。

    event_bus：Step 6.1 Dashboard 事件总线。测试可注入 Mock，
    生产传 EventBus() 实例。为 None 时不启动广播协程。
    enable_auth：测试可传 False 跳过鉴权中间件（默认 True）。
    lifespan：FastAPI lifespan 上下文管理器（替代已移除的 on_event）。
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.11.0",
        description="轻量级多Agent软件开发自循环系统",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
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
    # 懒加载路由注册——routes=None=全部，routes=[...]=仅指定路由
    _active = routes if routes is not None else list(_ROUTE_SPEC.keys())
    for name in _active:
        if name not in _ROUTE_SPEC:
            continue
        router, prefix = _lazy_import(name)
        app.include_router(router, prefix=prefix) if prefix else app.include_router(router)
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

    # ClarifierAgent 用 Flash 轻量模型（仅当 chat 路由被加载时）
    from orbit.gateway.client import LLMClient as _LLMClient
    if "chat" in _active:
        import importlib
        _chat_mod = importlib.import_module("orbit.api.routes.chat")
        _chat_mod.set_clarifier_llm(_LLMClient(default_model=MODEL_FLASH))

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

importlib.import_module("orbit.api.routes.review").set_review_service(_review_service)
importlib.import_module("orbit.api.routes.files_routes").set_file_service(_file_service)
importlib.import_module("orbit.api.routes.git_routes").set_workspace_dir(_ws_dir)
# Step 9 Phase 1.3: CodeGraph 引擎——复用 graph 数据库连接
from orbit.graph.engines.code_graph import CodeGraphEngine  # noqa: E402

_code_graph_engine = CodeGraphEngine(_review_session_factory)

importlib.import_module("orbit.api.routes.codegraph_routes").set_code_graph(_code_graph_engine)
importlib.import_module("orbit.api.routes.codegraph_routes").set_file_service(_file_service)
importlib.import_module("orbit.api.routes.insights_routes").set_code_graph(_code_graph_engine)
importlib.import_module("orbit.api.routes.insights_routes").set_review_service(_review_service)
importlib.import_module("orbit.api.routes.compliance_routes").set_file_service(_file_service)
importlib.import_module("orbit.api.routes.search_routes").set_workspace(_ws_dir)
importlib.import_module("orbit.api.routes.tests_routes").set_workspace(_ws_dir)
# Step 9 Phase 2: 诊断服务
from orbit.lsp.service import DiagnosticService  # noqa: E402

_diagnostic_service = DiagnosticService(_ws_dir)

importlib.import_module("orbit.api.routes.blame_routes").set_workspace(_ws_dir)
importlib.import_module("orbit.api.routes.terminal_routes").set_workspace(_ws_dir)
importlib.import_module("orbit.api.routes.diagnostics_ws").set_diagnostic_service(_diagnostic_service)


# ── MCP 客户端：连接外部 MCP 服务器 ──
def _load_and_connect_mcp(registry: ToolRegistry) -> None:
    """从 YAML 配置加载并连接 MCP 服务器。

    WHY 独立函数: 启动逻辑可复用。失败降级不阻断 Orbit 启动。
    """
    import yaml

    config_path = Path(settings.WORKSPACE_DIR or os.getcwd()) / "configs" / "mcp_clients.yaml"
    if not config_path.exists():
        logger.info("mcp_no_config", path=str(config_path))
        return

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.warning("mcp_config_parse_failed", error=str(e))
        return

    for server in config.get("servers", []):
        name = server.get("name", "")
        if not name or not server.get("enabled", True):
            continue

        # WHY: 检测命令是否可执行——提前给出人类可读提示，而非等子进程报错
        command = server["command"]
        command_available = False
        try:
            command_available = shutil.which(command) is not None
        except Exception:
            pass

        if not command_available:
            logger.info(
                "mcp_command_not_found",
                server=name,
                command=command,
                hint=f"请安装: pip install {name}-agent 或 uv tool install {name}-agent",
            )
            # 不阻断——该服务器跳过，其他服务器继续
            continue

        try:
            n = registry.connect_mcp_server(
                name=name,
                command=command,
                args=server.get("args", []),
                timeout=server.get("timeout_seconds", 30),
            )
            logger.info("mcp_server_connected", server=name, tools_registered=n)
        except Exception as e:
            logger.warning("mcp_connect_failed", server=name, error=str(e))


# ── 应用生命周期（替代已移除的 on_event / add_event_handler）──
# WHY lifespan: FastAPI 0.136+/Starlette 0.49+ 移除了 add_event_handler，
# 所有启动/关闭逻辑必须统一到 lifespan 上下文管理器。
async def _app_lifespan(app: FastAPI) -> None:
    """统一管理所有启动/关闭逻辑。

    启动：EventBus 广播 → Actor Watchdog → 审查表建表 → 高峰避让调度器
    关闭：释放数据库连接池
    """
    # ── 启动阶段 ──
    # EventBus 广播 + Actor Watchdog（原 _startup_background）
    if _event_bus is not None:
        asyncio.create_task(start_broadcaster(_event_bus))
        logger.info("ws_broadcaster_started")
    asyncio.create_task(_actor_watchdog.run())
    logger.info("watchdog_started")

    # 审查模块建表（原 _init_review_tables）
    async with _review_engine.begin() as conn:
        await conn.run_sync(ReviewBase.metadata.create_all)

    # D13: 高峰避让延迟调度器（原 _init_offpeak）
    if settings.OFFPEAK_ENABLED:
        _peak_manager = PeakWindowManager(config_path=settings.OFFPEAK_CONFIG_PATH)
        _offpeak_queue = DeferredQueue(db_path=settings.OFFPEAK_DB_PATH)
        _offpeak_scheduler = OffPeakScheduler(
            peak_manager=_peak_manager,
            queue=_offpeak_queue,
            orchestrator=app.state.meta_orchestrator,
            preflight=PreFlightEstimator(),
        )
        await _offpeak_scheduler.start()
        app.state.offpeak_scheduler = _offpeak_scheduler
        app.state.peak_window_manager = _peak_manager
        logger.info("offpeak_scheduler_initialized", config_path=settings.OFFPEAK_CONFIG_PATH)

    # MCP 客户端：连接外部服务器（如 Serena）——启动时自动发现工具
    try:
        _load_and_connect_mcp(ToolRegistry.get_instance())
    except Exception:
        logger.exception("mcp_init_failed")

    yield  # 应用运行中

    # ── 关闭阶段 ──
    # MCP 客户端：断开所有外部连接
    try:
        ToolRegistry.get_instance().disconnect_mcp_servers()
    except Exception:
        pass
    await _review_engine.dispose()  # P0-8: 释放连接池


app = create_app(_event_bus, lifespan=_app_lifespan)



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

    # _init_offpeak 逻辑已迁移到 _app_lifespan()，此处仅 import 保持模块可用
