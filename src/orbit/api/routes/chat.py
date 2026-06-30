"""自然语言聊天 API (NL交互 PR #3 + Session PR #1 + 需求澄清 Agent 接入).

WebSocket 端点: ws://host:18888/api/v1/chat
接受文本输入 → 项目匹配(首轮) → ClarifierAgent 多轮澄清 → 确认转开发.

架构约束：chat 端点只调 ClarifierAgent.execute()，不直接接触 LLMClient。
数据流: 用户 ↔ chat端点 ↔ ClarifierAgent ↔ (LLMClient网关 ↔ litellm ↔ 真实LLM)
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orbit.agents.base import AgentInput
from orbit.agents.clarifier import ClarifierAgent, StructuredPRD, validate_prd
from orbit.context.matcher import ContextMatcher
from orbit.projects.registry import ProjectRegistry
from orbit.sessions.registry import SessionRegistry

router = APIRouter(prefix="/chat", tags=["chat"])
import asyncio as _asyncio

_goal_lock = _asyncio.Lock()

_registry = ProjectRegistry()
_session_registry = SessionRegistry()
# WHY 预注册：确保测试/生产的 ProjectRegistry 至少有一个项目可匹配
if _registry.count() == 0:
    _registry.register(
        "Orbit", description="多Agent开发自循环系统", tags=["agent", "python", "llm"]
    )
_matcher = ContextMatcher(_registry)

# ---- ClarifierAgent 实例（进程级单例）----
# WHY llm=None 默认：无 LLM key 时不报错，走 mock 模式（供 CI）
# 生产环境由调用方注入 LLMClient，这里延迟实例化
_clarifier_agent: ClarifierAgent | None = None


def get_clarifier() -> ClarifierAgent:
    """获取/创建 ClarifierAgent 单例。

    WHY 延迟初始化：LLMClient 依赖环境变量（API key），
    在首次使用时才实例化，避免 import 时报错。
    """
    global _clarifier_agent
    if _clarifier_agent is None:
        _clarifier_agent = ClarifierAgent(llm=None)  # 默认 mock，生产可 set_clarifier_llm() 注入
    return _clarifier_agent


def set_clarifier_llm(llm_client: Any) -> None:
    """注入真实 LLMClient（生产环境调用）。"""
    global _clarifier_agent
    _clarifier_agent = ClarifierAgent(llm=llm_client)


# WHY 模块级 import orjson: 避免热路径动态 import
try:
    import orjson as _fast_json
except ImportError:
    _fast_json = None  # type: ignore[assignment]


def _parse(raw: bytes | str) -> Any:
    return _fast_json.loads(raw) if _fast_json is not None else _json.loads(raw)


async def _send(ws: WebSocket, code: int, data: Any, message: str = "ok") -> None:
    """统一响应格式: {code, data, message}."""
    await ws.send_json({"code": code, "data": data, "message": message})


@router.websocket("")
async def chat_endpoint(ws: WebSocket) -> None:
    """自然语言聊天入口。

    接收 JSON:
      { "type": "chat", "text": "用户输入", "session_id": "...", "project_name": "..." }
      { "type": "confirm", "session_id": "...", "project_name": "...", "modified_prd": {...} }
    返回 JSON:
      { code, data: {type, reply, clarification_status, structured_prd, ...}, message }
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            # WHY 防恶意畴形 JSON: 两次解析均失败时返回错误而非崩溃
            try:
                payload = _parse(raw)
            except Exception:
                await _send(ws, 1, None, "无效的 JSON 格式")
                continue

            msg_type = payload.get("type", "chat")
            text = payload.get("text", "")
            session_id = payload.get("session_id", "")
            project_name = payload.get("project_name", "")

            if msg_type == "chat":
                await _handle_chat(ws, text, session_id, project_name, payload)
            elif msg_type == "confirm":
                modified_prd = payload.get("modified_prd")
                await _handle_confirm(ws, session_id, project_name, modified_prd)
            else:
                await _send(ws, 1, None, f"未知消息类型: {msg_type}")

    except WebSocketDisconnect:
        pass  # 客户端正常断开


# P1-2: Goal 后台任务异常回调
def _on_goal_task_done(goal_id: str, task) -> None:
    try:
        task.result()
    except Exception:
        import structlog

        structlog.get_logger("orbit.chat").error(
            "goal_background_failed", goal_id=goal_id, exc_info=True
        )


async def _handle_goal_command(ws: WebSocket, text: str) -> None:
    """/goal <desc> | /goal status | /goal clear."""
    from orbit.api.routes import goal as goal_route

    orch = getattr(ws.app.state, "meta_orchestrator", None)
    if orch is None:
        await _send(ws, 503, None, "MetaOrchestrator 未初始化")
        return
    cmd = text[5:].strip()
    if not cmd:
        await _send(ws, 1, None, "/goal <desc> | /goal status | /goal clear")
        return
    if cmd == "status":
        t = goal_route._active_task
        detail = (
            "idle"
            if t is None
            else (
                "cancelled"
                if t.cancelled()
                else (
                    "done"
                    if t.done() and not t.exception()
                    else ("failed" if t.done() else "running")
                )
            )
        )
        await _send(
            ws,
            0,
            {
                "active": t is not None and not t.done(),
                "goal_id": goal_route._active_goal_id,
                "status": detail,
            },
            "Goal 状态",
        )
        return
    if cmd == "clear":
        t = goal_route._active_task
        gid = goal_route._active_goal_id
        if t and not t.done():
            t.cancel()
            goal_route._active_task = None
            goal_route._active_goal_id = None
            await _send(ws, 0, {"goal_id": gid}, "Goal 已取消")
            return
        await _send(ws, 0, {}, "无活跃 Goal")
        return
    # 创建新 Goal: 先取消旧任务
    async with _goal_lock:
        old = goal_route._active_task
        if old and not old.done():
            old.cancel()
        from orbit.goal.models import GoalSession
        import asyncio

        goal = GoalSession(description=cmd)
        task = asyncio.create_task(orch.run(goal))
        task.add_done_callback(lambda t, gid=goal.id: _on_goal_task_done(gid, t))
        goal_route._active_task = task
        goal_route._active_goal_id = goal.id
        await _send(ws, 0, {"goal_id": goal.id, "status": "active"}, f"Goal 已启动")


def _on_goal_task_done(goal_id: str, task) -> None:
    try:
        task.result()
    except Exception:
        import structlog

        structlog.get_logger("orbit.chat").error(
            "goal_background_failed", goal_id=goal_id, exc_info=True
        )


async def _handle_chat(
    ws: WebSocket, text: str, session_id: str, project_name: str, payload: dict[str, Any]
) -> None:
    """处理用户聊天消息：项目匹配(首轮) + ClarifierAgent 澄清。"""
    if not text.strip():
        await _send(ws, 1, None, "输入为空")
        return

    # /goal 命令族
    if text.strip().startswith("/goal"):
        await _handle_goal_command(ws, text.strip())
        return

    # 验证 session 存在
    if session_id and _session_registry.get(session_id) is None:
        await _send(ws, 1, None, f"会话 {session_id} 不存在")
        return

    # ---- 构建上下文 ----
    # 对话历史（最近 10 轮 = 20 条）
    history: list[dict[str, Any]] = []
    if session_id:
        msgs = _session_registry.get_messages(session_id, limit=20)
        history = [{"role": m.role, "content": m.content} for m in msgs]

    # 项目信息（首轮匹配或从 project_name 查）
    project_info: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    if not history:
        # 首轮：跑 ContextMatcher 匹配项目
        session_projects = payload.get("session_projects")
        match_result = _matcher.match(text, session_projects=session_projects)
        candidates = match_result.to_dict().get("candidates", [])
        if match_result.candidates:
            top = match_result.candidates[0]
            proj = _registry.get(top.project_name)
            if proj:
                project_info = {
                    "name": proj.name,
                    "description": proj.description,
                    "tags": proj.tags,
                }

    if not project_info and project_name:
        proj = _registry.get(project_name)
        if proj:
            project_info = {
                "name": proj.name,
                "description": proj.description,
                "tags": proj.tags,
            }

    # ---- 调用 ClarifierAgent（不直接接触 LLM）----
    agent_input = AgentInput(
        task=text,
        context={
            "project": project_info,
            "history": history,
            "confirmed": {},
            "session_id": session_id,
            "project_name": project_name,
        },
        role="clarifier",  # type: ignore[arg-type]
    )
    agent = get_clarifier()
    output = await agent.execute(agent_input)

    result_data: dict[str, Any] = {
        "type": "clarify",
        "reply": output.result.get("reply", ""),
        "clarification_status": output.result.get("clarification_status", "clarifying"),
        "structured_prd": output.result.get("structured_prd"),
        "missing_fields": output.result.get("missing_fields", []),
        "agent_role": "Clarifier",
    }
    # 首轮带项目匹配结果
    if candidates:
        result_data["candidates"] = candidates

    # ---- ClarifierAgent 输出 ready 时，过 V1-V3 校验 ----
    prd_raw = output.result.get("structured_prd")
    if result_data["clarification_status"] == "ready" and prd_raw:
        validation = validate_prd(prd_raw)
        if not validation.passed:
            # 校验不过 → 打回 Agent 汇报（这里仅通知前端本轮未 ready，下轮重问）
            result_data["clarification_status"] = "clarifying"
            result_data["reply"] = (
                result_data["reply"]
                + "\n\n（需求尚未完全明确："
                + "；".join(validation.reasons)
                + "）"
            )
            result_data["missing_fields"] = list(
                set(result_data.get("missing_fields", []) + validation.reasons)
            )
            result_data["structured_prd"] = None

    # ---- 持久化用户消息 + Agent 回复 ----
    if session_id:
        try:
            _session_registry.add_message(
                session_id=session_id,
                role="user",
                content=text,
            )
            _session_registry.add_message(
                session_id=session_id,
                role="agent",
                content=result_data["reply"],
                candidates=candidates or None,
            )
            _session_registry.touch(session_id)
        except Exception:
            pass  # 持久化失败不阻塞聊天

    await _send(ws, 0, result_data)


async def _handle_confirm(
    ws: WebSocket, session_id: str, project_name: str, modified_prd: dict[str, Any] | None
) -> None:
    """处理用户确认 PRD：重过 V1-V3，通过则建任务转开发。"""
    # 从 session 历史取上轮 ready 的 PRD，或用户修改版
    prd_data = modified_prd
    if prd_data is None:
        # 取最近一条 agent 消息中的 structured_prd（待扩展：当前 ChatMessageRecord 不存 PRD，先检查 modified_prd）
        await _send(ws, 1, None, "请先提供确认的需求 PRD（点击确认时携带 modified_prd）")
        return

    # 重过 V1-V3（用户修改后需重新校验）
    validation = validate_prd(prd_data)
    if not validation.passed:
        await _send(
            ws,
            1,
            {"validation": validation.model_dump()},
            "需求校验未通过：" + "；".join(validation.reasons),
        )
        return

    # ---- V1-V3 通过，序列化 PRD 并建任务 ----
    prd = StructuredPRD.model_validate(prd_data)
    prd_text = _json.dumps(prd.model_dump(), ensure_ascii=False, indent=2)

    # 校验字符数约束（TaskCreateRequest.prd 10-5000）
    if len(prd_text) < 10:
        await _send(ws, 1, None, "PRD 内容过短")
        return

    try:
        from orbit.api.routes.tasks import create_task as _create_task
        from orbit.api.schemas.task import TaskCreateRequest

        # 内部调用：构造 TaskCreateRequest，复用现有任务创建逻辑
        task_req = TaskCreateRequest(
            prd=prd_text[:5000],  # 截断到上限
            session_id=session_id or None,
        )
        task_resp = await _create_task(task_req)
        task_id = task_resp.task_id

        import asyncio as _asyncio

        try:
            from orbit.api.main import _scheduler

            if _scheduler is not None:
                _asyncio.create_task(_scheduler.run_task(task_id, prd_text[:5000]))
        except Exception as e:
            import structlog as _sl

            _sl.get_logger().warning("run_task_trigger_failed", task_id=task_id, error=str(e))

        await _send(
            ws,
            0,
            {
                "type": "task_created",
                "task_id": task_id,
                "state": task_resp.state.value,
                "message": "已创建任务，进入开发流程",
            },
        )
    except Exception as e:
        await _send(ws, 1, None, f"创建任务失败: {e}")
