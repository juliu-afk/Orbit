"""跨 Agent Grilling 工具——query_upstream / trace_upstream / request_human_clarification。

V15.3 US2: grill-me 跨 Agent 化。
Agent 发现上下文不足时，通过三级工具向上追溯：
  1. query_upstream  → 向指定上游 Agent 查询
  2. trace_upstream  → 自动溯链直到找到答案
  3. request_human_clarification → 全链无答案时请求人类协助
"""

from __future__ import annotations

import hashlib
import json as _json
import time
from typing import Any

import structlog

from orbit.agents.context_util import GrillRequest

logger = structlog.get_logger("orbit.agents.grill")

# 人类求助上限——防止骚扰用户
_MAX_HUMAN_ESCALATIONS = 3
# 上游链顺序（trace_upstream 用）
_UPSTREAM_CHAIN = {
    "developer": ["architect", "clarifier", "chatter"],
    "reviewer": ["developer", "architect", "clarifier", "chatter"],
    "qa": ["developer", "architect", "clarifier", "chatter"],
    "architect": ["clarifier", "chatter"],
    "clarifier": ["chatter"],
}


async def _record_grill(
    task_id: str,
    asking_agent: str,
    answering_agent: str,
    question: str,
    answer: str,
) -> None:
    """记录 Grilling 交互到 grill_log——供 US7 反馈进化。"""
    try:
        from orbit.sessions.registry import SessionRegistry
        import sqlite3

        registry = SessionRegistry()
        conn = registry._get_conn()
        now = time.time()
        qh = hashlib.md5(question.encode()).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO grill_log "
            "(task_id, asking_agent, answering_agent, question_hash, question_json, answer_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, asking_agent, answering_agent, qh, question, answer, now),
        )
        conn.commit()
    except Exception:
        pass  # fail-open: Grill 记录失败不影响主流程


async def query_upstream(params: dict) -> dict:
    """向指定上游 Agent 查询信息。

    GrillRequest 必填字段由 Pydantic 校验——裸问题被拒绝。

    Returns:
        {answer, source_agent, cached}
    """
    try:
        grill = GrillRequest(**params)
    except Exception as e:
        return {"status": "rejected", "reason": f"GrillRequest 校验失败: {e}"}

    task_id = params.get("_task_id", "")
    asking_agent = params.get("_agent_role", "unknown")
    target = grill.target_agent

    # 去重检查
    qh = hashlib.md5(grill.question.encode()).hexdigest()
    try:
        from orbit.sessions.registry import SessionRegistry
        registry = SessionRegistry()
        conn = registry._get_conn()
        row = conn.execute(
            "SELECT answer_text FROM grill_log WHERE question_hash=? AND task_id=?",
            (qh, task_id),
        ).fetchone()
        if row and row[0]:
            return {"answer": row[0], "source_agent": "cache", "cached": True}
    except Exception:
        pass

    # 路由到上游 Agent——通过 context/artifacts 搜索
    answer = ""
    source = target or "artifacts"

    try:
        from orbit.integration.wiring import get_wiring
        wiring = get_wiring()
        if wiring:
            # 尝试从工件中检索
            ctx = wiring._get_context_for_agent(target) if target else {}
            if ctx:
                answer = _json.dumps(ctx, ensure_ascii=False, default=str)[:2000]
                source = target or "context"
    except Exception:
        pass

    if not answer:
        answer = f"[上游 {target or 'artifacts'} 暂无相关信息]"
        source = "unavailable"

    await _record_grill(task_id, asking_agent, source, grill.question, answer)
    return {"answer": answer, "source_agent": source, "cached": False}


async def trace_upstream(params: dict) -> dict:
    """自动向 Agent 链上游溯源直到找到答案。

    搜索链: 当前 Agent → 链式上游 → 人类求助。
    """
    try:
        grill = GrillRequest(**params)
    except Exception as e:
        return {"status": "rejected", "reason": f"GrillRequest 校验失败: {e}"}

    asking_agent = params.get("_agent_role", "unknown")
    chain = _UPSTREAM_CHAIN.get(asking_agent, ["architect", "clarifier", "chatter"])

    for upstream in chain:
        grill.target_agent = upstream
        result = await query_upstream({**params, "target_agent": upstream})
        answer = result.get("answer", "")
        if answer and "暂无相关信息" not in str(answer):
            return {
                "answer": answer,
                "source_agent": upstream,
                "trace_path": chain[: chain.index(upstream) + 1],
            }

    # 全链无答案 → 人类求助
    human_result = await request_human_clarification(params)
    return {
        "answer": human_result.get("answer", ""),
        "source_agent": "human",
        "trace_path": chain + ["human"],
        "escalated": True,
    }


async def request_human_clarification(params: dict) -> dict:
    """全链无答案时向人类用户请求澄清——最后手段。

    遵守上下文原则：告知用户为什么需要这个信息、影响什么决策。
    每任务 ≤ 3 次。
    """
    try:
        grill = GrillRequest(**params)
    except Exception as e:
        return {"status": "rejected", "reason": f"GrillRequest 校验失败: {e}"}

    task_id = params.get("_task_id", "")

    # 检查 HITL 配额
    try:
        from orbit.sessions.registry import SessionRegistry
        registry = SessionRegistry()
        conn = registry._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM grill_log WHERE task_id=? AND answering_agent='human'",
            (task_id,),
        ).fetchone()
        if row and row[0] >= _MAX_HUMAN_ESCALATIONS:
            return {
                "answer": "[已达人工求助上限] 请基于现有信息继续执行。",
                "source_agent": "human",
                "quota_exceeded": True,
            }
    except Exception:
        pass

    # 构建人类可读的请求
    question_text = (
        f"**问题**：{grill.question}\n\n"
        f"**背景**：{grill.background}\n"
    )
    if grill.conflict_detection:
        question_text += f"**⚠️ 冲突/模糊**：{grill.conflict_detection}\n"
    if grill.candidates:
        question_text += f"**候选方案**：{' / '.join(grill.candidates)}\n"
    if grill.impact:
        question_text += f"**影响面**：{grill.impact}\n"

    # 通过 HITLManager 推送给用户
    try:
        from orbit.metacognition.hitl import HITLManager
        hitl = HITLManager()
        hitl.request_clarification(task_id=task_id, question=question_text)
    except Exception:
        pass

    await _record_grill(task_id, params.get("_agent_role", "unknown"), "human", grill.question, "")
    return {
        "answer": f"[已向人类用户请求澄清]\n{question_text}",
        "source_agent": "human",
        "pending": True,
    }
