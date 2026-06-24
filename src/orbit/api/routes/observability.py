"""可观测性 API（Step 7.2 AgentOps）。

GET  /observability/health             全组件健康状态
GET  /observability/health/{component}  单组件健康状态
GET  /observability/metrics            业务指标快照
GET  /observability/alerts             当前活跃告警
GET  /observability/alerts/history     告警历史
GET  /observability/audit              审计日志（按 task_id）
POST /observability/lessons            记录教训
GET  /observability/lessons            查询教训库
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from orbit.observability.alerts import AlertEngine
from orbit.observability.audit import AuditLogger, LessonStore
from orbit.observability.collector import ComponentStatus, HealthCollector
from orbit.observability.metrics import snapshot as metrics_snapshot
from orbit.observability.probes import StartupProbeEngine

router = APIRouter(prefix="/observability", tags=["observability"])

# ── 模块级单例 ────────────────────────────────────────────

_collector = HealthCollector()
_alert_engine = AlertEngine()
_alert_engine.add_builtin_rules()
_audit = AuditLogger()
_lessons = LessonStore()

# 注册核心组件（已有逻辑）
for _comp in [
    "scheduler",
    "llm_gateway",
    "code_graph",
    "db_graph",
    "config_graph",
    "hallucination_layers",
    "sandbox",
    "knowledge_engine",
]:
    _collector.register(_comp)


# ── 健康检查（已有） ──────────────────────────────────────


@router.get("/health", summary="全组件健康状态")
async def observability_health() -> dict[str, Any]:
    """返回所有核心组件的健康状态摘要。"""
    _collector.update("scheduler", ComponentStatus.HEALTHY)
    _collector.update("knowledge_engine", ComponentStatus.HEALTHY)
    _collector.update("llm_gateway", ComponentStatus.HEALTHY)
    # WHY ?????CodeGraphEngine ?????????????????
    try:
        from orbit.graph.engines.code_graph import CodeGraphEngine

        _ = CodeGraphEngine  # noqa: F841
        _collector.update("code_graph", ComponentStatus.HEALTHY)
    except ImportError:
        _collector.update("code_graph", ComponentStatus.DEGRADED, "?????????")
    _collector.update("db_graph", ComponentStatus.HEALTHY)
    _collector.update("config_graph", ComponentStatus.HEALTHY)
    _collector.update("hallucination_layers", ComponentStatus.HEALTHY)
    _collector.update("sandbox", ComponentStatus.HEALTHY)
    return _collector.summary()


@router.get("/health/{component}", summary="单组件健康状态")
async def component_health(component: str) -> dict[str, Any]:
    """返回单个组件的健康状态。"""
    c = _collector.get(component)
    if c is None:
        return {"error": f"未知组件: {component}"}
    return {
        "name": c.name,
        "status": c.status.value,
        "message": c.message,
        "metrics": c.metrics,
    }


# ── 业务指标（新增） ──────────────────────────────────────


@router.get("/metrics", summary="业务指标快照")
async def observability_metrics() -> dict[str, Any]:
    """返回所有业务指标的当前快照。

    与 /metrics (Prometheus) 互补：本端点返回 JSON 格式，
    供驾驶舱前端直接消费。
    """
    return {"code": 0, "data": metrics_snapshot(), "message": "ok"}


# ── 告警（新增） ──────────────────────────────────────────


@router.get("/alerts", summary="当前活跃告警")
async def observability_alerts() -> dict[str, Any]:
    """返回当前活跃告警列表（冷却期内的告警仍视为活跃）。"""
    # 评估一次指标，触发告警检查
    _alert_engine.evaluate(metrics_snapshot())
    return {"code": 0, "data": _alert_engine.get_active(), "message": "ok"}


@router.get("/alerts/history", summary="告警历史")
async def observability_alerts_history(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """返回告警历史记录（最多 200 条）。"""
    return {
        "code": 0,
        "data": _alert_engine.get_history(limit=limit),
        "message": "ok",
    }


# ── 审计（新增） ──────────────────────────────────────────


@router.get("/audit", summary="审计日志查询")
async def observability_audit(
    task_id: str = Query(default="", description="按任务 ID 过滤，为空返回空列表"),
) -> dict[str, Any]:
    """按 task_id 查询审计相关教训记录。

    WHY 不返回 structlog 实时流：
    structlog 输出到 stdout，由容器日志系统采集。
    本端点返回 SQLite 中持久化的教训记录。
    """
    if not task_id:
        return {"code": 0, "data": [], "message": "ok"}
    lessons = _lessons.list_by_task(task_id)
    return {
        "code": 0,
        "data": [
            {
                "lesson_id": ls.lesson_id,
                "task_id": ls.task_id,
                "domain": ls.domain,
                "outcome": ls.outcome,
                "lesson": ls.lesson,
                "tags": ls.tags,
                "created_at": ls.created_at,
            }
            for ls in lessons
        ],
        "message": "ok",
    }


# ── 教训库（新增） ────────────────────────────────────────


@router.post("/lessons", summary="记录教训", status_code=201)
async def create_lesson(
    task_id: str = Query(default=""),
    domain: str = Query(default=""),
    outcome: str = Query(default="success"),
    lesson: str = Query(default=""),
    tags: str = Query(default=""),
) -> dict[str, Any]:
    """记录一条成功/失败教训到教训库。

    领域（domain）：scheduler | llm | sandbox | graph | hallucination
    结果（outcome）：success | failure
    """
    if not task_id or not domain or not lesson:
        raise HTTPException(status_code=422, detail="task_id, domain, lesson 必填")
    if outcome not in ("success", "failure"):
        raise HTTPException(status_code=422, detail="outcome 必须为 success 或 failure")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    result = _lessons.add(
        task_id=task_id,
        domain=domain,
        outcome=outcome,  # type: ignore[arg-type]
        lesson=lesson,
        tags=tag_list,
    )
    return {
        "code": 0,
        "data": {
            "lesson_id": result.lesson_id,
            "task_id": result.task_id,
            "outcome": result.outcome,
            "lesson": result.lesson,
        },
        "message": "ok",
    }


@router.get("/lessons", summary="查询教训库")
async def list_lessons(
    domain: str = Query(default="", description="按领域过滤，为空返回统计"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """按领域查询教训记录。"""
    if domain:
        lessons = _lessons.list_by_domain(domain, limit=limit)
    else:
        return {
            "code": 0,
            "data": {
                "total": _lessons.count(),
                "hint": "使用 ?domain=scheduler 按领域过滤",
            },
            "message": "ok",
        }
    return {
        "code": 0,
        "data": [
            {
                "lesson_id": ls.lesson_id,
                "task_id": ls.task_id,
                "domain": ls.domain,
                "outcome": ls.outcome,
                "lesson": ls.lesson,
                "tags": ls.tags,
                "created_at": ls.created_at,
            }
            for ls in lessons
        ],
        "message": "ok",
    }


# ── 启动预检（Session PR 后续） ────────────────────────────

_probe_engine: StartupProbeEngine | None = None
_probe_lock = asyncio.Lock()


@router.get("/startup-probe", summary="启动预检探针")
async def startup_probe() -> dict[str, Any]:
    """返回启动探针执行状态。首次请求触发异步执行。"""
    global _probe_engine
    if _probe_engine is None:
        async with _probe_lock:
            if _probe_engine is None:
                engine = StartupProbeEngine()
                asyncio.create_task(engine.start())
                _probe_engine = engine
    return {"code": 0, "data": _probe_engine.results(), "message": "ok"}


@router.post("/startup-probe/reset", summary="重置并重试启动探针")
async def startup_probe_reset() -> dict[str, Any]:
    """重置失败探针，重新运行。"""
    global _probe_engine
    if _probe_engine is not None:
        _probe_engine.reset()
        asyncio.create_task(_probe_engine.start())
    return {"code": 0, "data": {"status": "reset"}, "message": "ok"}


@router.post("/startup-probe/install/{name}", summary="安装指定组件")
async def startup_probe_install(name: str) -> dict[str, Any]:
    """后台安装指定组件（如 Docker Desktop）。"""
    if name == "docker":

        asyncio.create_task(_async_install_docker())
        return {
            "code": 0,
            "data": {"status": "installing"},
            "message": "正在后台安装 Docker Desktop...",
        }
    raise HTTPException(status_code=404, detail=f"未知组件: {name}")


async def _async_install_docker() -> None:
    """后台安装 Docker，完成后重置 sandbox 探针并重跑。"""
    from orbit.observability.probes import install_docker

    global _probe_engine
    result = await install_docker()
    if _probe_engine is not None:
        # 只重置 sandbox 探针
        for check in _probe_engine._checks:
            if check.name == "sandbox":
                check.status = "pending"
                check.message = result
                check.install_action = None
                check.auto_repaired = False
                break
        # 重跑 sandbox
        for check in _probe_engine._checks:
            if check.name == "sandbox" and check.status == "pending":
                await _probe_engine._run_probe(check)
                break
