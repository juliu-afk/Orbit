"""å¯è§æµæ§ APIï¼Step 7.2 AgentOpsï¼ã

GET  /observability/health             å
¨ç»ä»¶å¥åº·ç¶æ
GET  /observability/health/{component}  åç»ä»¶å¥åº·ç¶æ
GET  /observability/metrics            ä¸å¡ææ å¿«ç
§
GET  /observability/alerts             å½åæ´»è·åè­¦
GET  /observability/alerts/history     åè­¦åå²
GET  /observability/audit              å®¡è®¡æ¥å¿ï¼æ task_idï¼
POST /observability/lessons            è®°å½æè®­
GET  /observability/lessons            æ¥è¯¢æè®­åº
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

# ââ æ¨¡åçº§åä¾ ââââââââââââââââââââââââââââââââââââââââââââ

_collector = HealthCollector()
_alert_engine = AlertEngine()
_alert_engine.add_builtin_rules()
_audit = AuditLogger()
_lessons = LessonStore()

# æ³¨åæ ¸å¿ç»ä»¶ï¼å·²æé»è¾ï¼
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


# ââ å¥åº·æ£æ¥ï¼å·²æï¼ ââââââââââââââââââââââââââââââââââââââ


@router.get("/health", summary="å¨ç»ä»¶å¥åº·ç¶æ")
async def observability_health() -> dict[str, Any]:
    """è¿åæææ ¸å¿ç»ä»¶çå¥åº·ç¶ææè¦ã"""
    _collector.update("scheduler", ComponentStatus.HEALTHY)
    _collector.update("knowledge_engine", ComponentStatus.HEALTHY)
    _collector.update("llm_gateway", ComponentStatus.HEALTHY)
    # 真实检测：CodeGraphEngine 可导入即健康
    try:
        from orbit.graph.engines.code_graph import CodeGraphEngine

        _ = CodeGraphEngine  # noqa: F841
        _collector.update("code_graph", ComponentStatus.HEALTHY)
    except ImportError:
        _collector.update("code_graph", ComponentStatus.DEGRADED, "代码图谱模块不可用")
    _collector.update("db_graph", ComponentStatus.HEALTHY)
    _collector.update("config_graph", ComponentStatus.HEALTHY)
    _collector.update("hallucination_layers", ComponentStatus.HEALTHY)
    _collector.update("sandbox", ComponentStatus.HEALTHY)
    return _collector.summary()


@router.get("/health/{component}", summary="åç»ä»¶å¥åº·ç¶æ")
async def component_health(component: str) -> dict[str, Any]:
    """è¿ååä¸ªç»ä»¶çå¥åº·ç¶æã"""
    c = _collector.get(component)
    if c is None:
        return {"error": f"æªç¥ç»ä»¶: {component}"}
    return {
        "name": c.name,
        "status": c.status.value,
        "message": c.message,
        "metrics": c.metrics,
    }


# ââ ä¸å¡ææ ï¼æ°å¢ï¼ ââââââââââââââââââââââââââââââââââââââ


@router.get("/metrics", summary="ä¸å¡ææ å¿«ç§")
async def observability_metrics() -> dict[str, Any]:
    """è¿åææä¸å¡ææ çå½åå¿«ç
    §ã

        ä¸ /metrics (Prometheus) äºè¡¥ï¼æ¬ç«¯ç¹è¿å JSON æ ¼å¼ï¼
        ä¾é©¾é©¶è±åç«¯ç´æ¥æ¶è´¹ã
    """
    return {"code": 0, "data": metrics_snapshot(), "message": "ok"}


# ââ åè­¦ï¼æ°å¢ï¼ ââââââââââââââââââââââââââââââââââââââââââ


@router.get("/alerts", summary="å½åæ´»è·åè­¦")
async def observability_alerts() -> dict[str, Any]:
    """è¿åå½åæ´»è·åè­¦åè¡¨ï¼å·å´æåçåè­¦ä»è§ä¸ºæ´»è·ï¼ã"""
    # è¯ä¼°ä¸æ¬¡ææ ï¼è§¦ååè­¦æ£æ¥
    _alert_engine.evaluate(metrics_snapshot())
    return {"code": 0, "data": _alert_engine.get_active(), "message": "ok"}


@router.get("/alerts/history", summary="åè­¦åå²")
async def observability_alerts_history(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """è¿ååè­¦åå²è®°å½ï¼æå¤ 200 æ¡ï¼ã"""
    return {
        "code": 0,
        "data": _alert_engine.get_history(limit=limit),
        "message": "ok",
    }


# ââ å®¡è®¡ï¼æ°å¢ï¼ ââââââââââââââââââââââââââââââââââââââââââ


@router.get("/audit", summary="å®¡è®¡æ¥å¿æ¥è¯¢")
async def observability_audit(
    task_id: str = Query(default="", description="æä»»å¡ ID è¿æ»¤ï¼ä¸ºç©ºè¿åç©ºåè¡¨"),
) -> dict[str, Any]:
    """æ task_id æ¥è¯¢å®¡è®¡ç¸å
    ³æè®­è®°å½ã

        WHY ä¸è¿å structlog å®æ¶æµï¼
        structlog è¾åºå° stdoutï¼ç±å®¹å¨æ¥å¿ç³»ç»ééã
        æ¬ç«¯ç¹è¿å SQLite ä¸­æä¹
    åçæè®­è®°å½ã
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


# ââ æè®­åºï¼æ°å¢ï¼ ââââââââââââââââââââââââââââââââââââââââ


@router.post("/lessons", summary="è®°å½æè®­", status_code=201)
async def create_lesson(
    task_id: str = Query(default=""),
    domain: str = Query(default=""),
    outcome: str = Query(default="success"),
    lesson: str = Query(default=""),
    tags: str = Query(default=""),
) -> dict[str, Any]:
    """è®°å½ä¸æ¡æå/å¤±è´¥æè®­å°æè®­åºã

    é¢åï¼domainï¼ï¼scheduler | llm | sandbox | graph | hallucination
    ç»æï¼outcomeï¼ï¼success | failure
    """
    if not task_id or not domain or not lesson:
        raise HTTPException(status_code=422, detail="task_id, domain, lesson å¿å¡«")
    if outcome not in ("success", "failure"):
        raise HTTPException(status_code=422, detail="outcome å¿é¡»ä¸º success æ failure")

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


@router.get("/lessons", summary="æ¥è¯¢æè®­åº")
async def list_lessons(
    domain: str = Query(default="", description="æé¢åè¿æ»¤ï¼ä¸ºç©ºè¿åç»è®¡"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """æé¢åæ¥è¯¢æè®­è®°å½ã"""
    if domain:
        lessons = _lessons.list_by_domain(domain, limit=limit)
    else:
        return {
            "code": 0,
            "data": {
                "total": _lessons.count(),
                "hint": "ä½¿ç¨ ?domain=scheduler æé¢åè¿æ»¤",
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


# ââ å¯å¨é¢æ£ï¼Session PR åç»­ï¼ ââââââââââââââââââââââââââââ

_probe_engine: StartupProbeEngine | None = None
_probe_lock = asyncio.Lock()


@router.get("/startup-probe", summary="å¯å¨é¢æ£æ¢é")
async def startup_probe() -> dict[str, Any]:
    """è¿åå¯å¨æ¢éæ§è¡ç¶æãé¦æ¬¡è¯·æ±è§¦åå¼æ­¥æ§è¡ã"""
    global _probe_engine
    if _probe_engine is None:
        async with _probe_lock:
            if _probe_engine is None:
                engine = StartupProbeEngine()
                asyncio.create_task(engine.start())
                _probe_engine = engine
    return {"code": 0, "data": _probe_engine.results(), "message": "ok"}


@router.post("/startup-probe/reset", summary="éç½®å¹¶éè¯å¯å¨æ¢é")
async def startup_probe_reset() -> dict[str, Any]:
    """éç½®å¤±è´¥æ¢éï¼éæ°è¿è¡ã"""
    global _probe_engine
    if _probe_engine is not None:
        _probe_engine.reset()
        asyncio.create_task(_probe_engine.start())
    return {"code": 0, "data": {"status": "reset"}, "message": "ok"}


@router.post("/startup-probe/install/{name}", summary="å®è£æå®ç»ä»¶")
async def startup_probe_install(name: str) -> dict[str, Any]:
    """åå°å®è£æå®ç»ä»¶ï¼å¦ Docker Desktopï¼ã"""
    if name == "docker":

        asyncio.create_task(_async_install_docker())
        return {
            "code": 0,
            "data": {"status": "installing"},
            "message": "æ­£å¨åå°å®è£ Docker Desktop...",
        }
    raise HTTPException(status_code=404, detail=f"æªç¥ç»ä»¶: {name}")


async def _async_install_docker() -> None:
    """åå°å®è£ Dockerï¼å®æåéç½® sandbox æ¢éå¹¶éè·ã"""
    from orbit.observability.probes import install_docker

    global _probe_engine
    result = await install_docker()
    if _probe_engine is not None:
        # åªéç½® sandbox æ¢é
        for check in _probe_engine._checks:
            if check.name == "sandbox":
                check.status = "pending"
                check.message = result
                check.install_action = None
                check.auto_repaired = False
                break
        # éè· sandbox
        for check in _probe_engine._checks:
            if check.name == "sandbox" and check.status == "pending":
                await _probe_engine._run_probe(check)
                break
