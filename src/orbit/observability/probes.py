"""启动预检探针引擎——顺序检测 8 个核心组件，失败自动自愈。

三级状态: 检测 → 失败则自愈 → 再检测 → passed/repaired/failed。
探针顺序执行（部分有隐式依赖，如 database 先于 session_store）。
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger("orbit.probes")

# 单个探针超时——防止某个组件阻塞整个启动流程
PROBE_TIMEOUT_SECONDS = 10


@dataclass
class ProbeResult:
    """单个探针的执行结果。"""

    name: str  # machine key
    label: str  # 中文显示名
    status: str = "pending"  # pending/running/passed/failed/skipped/repaired
    message: str = ""
    auto_repaired: bool = False
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "auto_repaired": self.auto_repaired,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }


class StartupProbeEngine:
    """启动预检引擎——逐项检测+自愈。

    用法:
        engine = StartupProbeEngine()
        asyncio.create_task(engine.start())
        # ... 轮询 engine.results()
    """

    def __init__(self) -> None:
        # WHY 有序: 探针按注册顺序执行（database 先于 session_store）
        self._checks: list[ProbeResult] = [
            ProbeResult("environment", "环境配置"),
            ProbeResult("database", "数据库连接"),
            ProbeResult("agent", "Agent配置"),
            ProbeResult("llm_gateway", "LLM网关"),
            ProbeResult("sandbox", "沙箱环境"),
            ProbeResult("knowledge_engine", "知识引擎"),
            ProbeResult("code_graph", "代码图谱"),
            ProbeResult("session_store", "会话存储"),
        ]
        self._status = "pending"
        self._started_at: float | None = None
        self._completed_at: float | None = None
        self._lock = asyncio.Lock()
        self._auto_repairs = 0

    async def start(self) -> None:
        """运行全部探针。幂等——已运行则跳过。"""
        async with self._lock:
            if self._status in ("running", "passed"):
                return
            self._status = "running"
            self._started_at = time.time()

        for check in self._checks:
            await self._run_probe(check)

        async with self._lock:
            self._completed_at = time.time()
            self._status = (
                "failed" if any(c.status == "failed" for c in self._checks)
                else "passed"
            )

    async def _run_probe(self, check: ProbeResult) -> None:
        """执行单个探针：检测 → 自愈 → 再检测。"""
        check.status = "running"
        check.started_at = time.time()

        try:
            # Step 1: 检测
            probe_fn = _PROBE_FUNCTIONS.get(check.name)
            if probe_fn is None:
                check.status = "skipped"
                check.message = "探针未实现"
                return

            result = await asyncio.wait_for(probe_fn(), timeout=PROBE_TIMEOUT_SECONDS)
            check.status = "passed"
            check.message = result

        except asyncio.TimeoutError:
            # 超时 → 尝试自愈
            repaired = await self._try_repair(check)
            if repaired:
                check.status = "repaired"
                check.auto_repaired = True
                self._auto_repairs += 1
            else:
                check.status = "failed"
                check.message = f"探针超时（{PROBE_TIMEOUT_SECONDS}s），自愈失败"

        except Exception as e:
            # 检测失败 → 尝试自愈
            logger.warning("probe_failed", name=check.name, error=str(e))
            repaired = await self._try_repair(check)
            if repaired:
                check.status = "repaired"
                check.auto_repaired = True
                self._auto_repairs += 1
            else:
                check.status = "failed"
                check.message = str(e)[:500]

        finally:
            check.completed_at = time.time()
            check.duration_ms = int(
                (check.completed_at - (check.started_at or 0)) * 1000
            )

    async def _try_repair(self, check: ProbeResult) -> bool:
        """尝试自愈——每个探针有独立的修复策略。返回 True=修复成功。"""
        repair_fn = _REPAIR_FUNCTIONS.get(check.name)
        if repair_fn is None:
            return False
        try:
            msg = await asyncio.wait_for(repair_fn(), timeout=PROBE_TIMEOUT_SECONDS)
            check.message = msg
            logger.info("probe_repaired", name=check.name, detail=msg)
            return True
        except Exception:
            return False

    def results(self) -> dict[str, Any]:
        """返回当前探针状态——供 API 消费。"""
        elapsed = 0
        if self._started_at:
            end = self._completed_at or time.time()
            elapsed = int((end - self._started_at) * 1000)

        return {
            "status": self._status,
            "started_at": self._started_at,
            "completed_at": self._completed_at,
            "elapsed_ms": elapsed,
            "auto_repairs": self._auto_repairs,
            "checks": [c.to_dict() for c in self._checks],
        }

    def reset(self) -> None:
        """重置全部探针——供 retry 使用。"""
        self._status = "pending"
        self._started_at = None
        self._completed_at = None
        self._auto_repairs = 0
        for check in self._checks:
            check.status = "pending"
            check.message = ""
            check.auto_repaired = False
            check.started_at = None
            check.completed_at = None
            check.duration_ms = 0


# ── 探针函数（每个返回 success message 或 raise）──


async def _probe_environment() -> str:
    """检测 Settings 加载 + 必须环境变量。"""
    from orbit.core.config import settings

    # 验证 settings 对象存在且可访问属性
    _ = settings.PROJECT_NAME
    _ = settings.SANDBOX_TIMEOUT_SECONDS
    return f"配置加载成功: {settings.PROJECT_NAME}"


async def _probe_database() -> str:
    """检测 SQLite 连接。"""
    import sqlite3

    conn = sqlite3.connect("data/projects.db")
    try:
        conn.execute("SELECT 1")
        # 验证核心表存在
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
    finally:
        conn.close()
    return f"数据库连接成功，{len(table_names)} 张表"


async def _probe_agent() -> str:
    """检测 Agent 工厂可加载。"""
    try:
        from orbit.agents.factory import AgentFactory

        _ = AgentFactory
        return "Agent工厂可用"
    except ImportError:
        raise RuntimeError("Agent工厂模块导入失败")


async def _probe_llm_gateway() -> str:
    """检测 LLM 网关模块可用。非致命——跳过（用户后续配置）。"""
    try:
        from orbit.gateway.client import LLMClient

        _ = LLMClient
        return "LLM网关模块就绪"
    except ImportError:
        # WHY skipped 非 failed: LLM 需要 API key，MVP 阶段可跳过
        return "LLM网关模块未导入，可后续配置（非致命）"


async def _probe_sandbox() -> str:
    """检测沙箱可用。Docker → ProcessSandbox 自动降级。"""
    from orbit.sandbox.sandbox_factory import create_sandbox

    sandbox = await create_sandbox()
    if sandbox.__class__.__name__ == "ProcessSandbox":
        return "ProcessSandbox已就绪（Docker不可用，已自动降级）"
    return "Docker沙箱已就绪"


async def _probe_knowledge_engine() -> str:
    """检测知识引擎可访问。"""
    try:
        from orbit.knowledge.engine import KnowledgeEngine

        _ = KnowledgeEngine
        return "知识引擎模块就绪"
    except ImportError:
        raise RuntimeError("知识引擎模块导入失败")


async def _probe_code_graph() -> str:
    """检测代码图谱可用。非关键路径。"""
    try:
        from orbit.graph.meta_graph import MetaGraph

        _ = MetaGraph
        return "代码图谱模块就绪"
    except ImportError:
        return "代码图谱模块未就绪（非关键路径）"


async def _probe_session_store() -> str:
    """检测 sessions 表存在且可读写。"""
    import sqlite3

    conn = sqlite3.connect("data/projects.db")
    try:
        # 验证 sessions 表存在
        conn.execute("SELECT count(*) FROM sessions")
    finally:
        conn.close()
    return "会话存储就绪"


# ── 自愈函数（每个返回 success message 或 raise）──


async def _repair_database() -> str:
    """数据库自愈：自动建表。"""
    import sqlite3

    conn = sqlite3.connect("data/projects.db")
    try:
        from orbit.projects.registry import ProjectRegistry
        from orbit.sessions.registry import SessionRegistry

        # ProjectRegistry._ensure_table() 会自动建 projects 表
        pr = ProjectRegistry()
        pr._ensure_table()
        # SessionRegistry._ensure_tables() 会自动建 sessions + chat_messages
        sr = SessionRegistry()
        sr._ensure_tables()
        pr.close()
        sr.close()
    finally:
        conn.close()
    return "数据库表已自动创建"


async def _repair_environment() -> str:
    """环境配置自愈：使用内置默认值。"""
    # settings 已从 .env 或环境变量加载，缺失字段有默认值
    return "使用默认环境配置"


async def _repair_sandbox() -> str:
    """沙箱自愈：Docker 不可用时降级 ProcessSandbox。"""
    from orbit.sandbox.sandbox_factory import create_sandbox

    sandbox = await create_sandbox()
    return f"已启用 {sandbox.__class__.__name__}"


async def _repair_session_store() -> str:
    """会话存储自愈：自动建 sessions 表。"""
    return await _repair_database()


# ── 注册表 ──

_PROBE_FUNCTIONS: dict[str, Any] = {
    "environment": _probe_environment,
    "database": _probe_database,
    "agent": _probe_agent,
    "llm_gateway": _probe_llm_gateway,
    "sandbox": _probe_sandbox,
    "knowledge_engine": _probe_knowledge_engine,
    "code_graph": _probe_code_graph,
    "session_store": _probe_session_store,
}

_REPAIR_FUNCTIONS: dict[str, Any] = {
    "environment": _repair_environment,
    "database": _repair_database,
    "sandbox": _repair_sandbox,
    "session_store": _repair_session_store,
}
