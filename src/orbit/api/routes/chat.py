"""自然语言聊天 API (NL交互 PR #3 + Session PR #1 + ChatterAgent 首触).

WebSocket 端点: ws://host:18888/api/v1/chat
接受文本输入 → ChatterAgent 首触(意图路由) → chat 直接回复 / programming 转 ClarifierAgent 多轮澄清 → 确认转开发.

架构约束：chat 端点只调 Agent.execute()，不直接接触 LLMClient。
数据流: 用户 ↔ chat端点 ↔ ChatterAgent(首触) → [chat→回复] | [programming→ClarifierAgent] ↔ (LLMClient网关 ↔ litellm ↔ 真实LLM)
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orbit.agents.base import AgentInput, AgentRole
from orbit.agents.chatter import ChatterAgent  # 通用对话——首触点
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

# ---- Agent 实例（进程级单例）----
# WHY llm=None 默认：无 LLM key 时不报错，走 mock 模式（供 CI）
# 生产环境由调用方注入 LLMClient，这里延迟实例化
_chatter_agent: ChatterAgent | None = None
_clarifier_agent: ClarifierAgent | None = None


def get_chatter() -> ChatterAgent:
    """获取/创建 ChatterAgent 单例——用户首触点。"""
    global _chatter_agent
    if _chatter_agent is None:
        _chatter_agent = ChatterAgent(llm=None)
    return _chatter_agent


def get_clarifier() -> ClarifierAgent:
    """获取/创建 ClarifierAgent 单例——需求澄清。"""
    global _clarifier_agent
    if _clarifier_agent is None:
        _clarifier_agent = ClarifierAgent(llm=None)
    return _clarifier_agent


def set_chatter_llm(llm_client: Any) -> None:
    """注入 ChatterAgent 真实 LLMClient（生产环境调用）。"""
    global _chatter_agent
    _chatter_agent = ChatterAgent(llm=llm_client)


def set_clarifier_llm(llm_client: Any) -> None:
    """注入 ClarifierAgent 真实 LLMClient（生产环境调用）。"""
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
        import asyncio

        from orbit.goal.models import GoalSession

        goal = GoalSession(description=cmd)
        task = asyncio.create_task(orch.run(goal))
        task.add_done_callback(lambda t, gid=goal.id: _on_goal_task_done(gid, t))
        goal_route._active_task = task
        goal_route._active_goal_id = goal.id
        await _send(ws, 0, {"goal_id": goal.id, "status": "active"}, "Goal 已启动")


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
    """处理用户聊天消息：ChatterAgent 首触 → 意图路由 → ClarifierAgent 澄清。"""
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

    # ---- 构建上下文（项目信息 + 对话历史）----
    history: list[dict[str, Any]] = []
    if session_id:
        msgs = _session_registry.get_messages(session_id, limit=20)
        history = [{"role": m.role, "content": m.content} for m in msgs]

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

    # ---- Phase 1: ChatterAgent 首触 + 意图路由 ----
    chatter_input = AgentInput(
        task=text,
        context={
            "project": project_info,
            "history": history,
            "session_id": session_id,
            "project_name": project_name,
        },
        role=AgentRole.CHATTER,
    )
    chatter_agent = get_chatter()
    chatter_output = await chatter_agent.execute(chatter_input)
    intent = chatter_output.result.get("_intent", "chat")
    chatter_reply = chatter_output.result.get("reply", "")

    # WHY 意图路由：chat → 直接返回，programming → 转 ClarifierAgent
    if intent != "programming":
        # 普通对话——直接返回 ChatterAgent 回复
        result_data: dict[str, Any] = {
            "type": "chat",
            "reply": chatter_reply,
            "agent_role": "Chatter",
        }
        if candidates:
            result_data["candidates"] = candidates

        if session_id:
            try:
                _session_registry.add_message(session_id=session_id, role="user", content=text)
                _session_registry.add_message(
                    session_id=session_id, role="agent", content=chatter_reply
                )
                _session_registry.touch(session_id)
            except Exception:
                pass

        await _send(ws, 0, result_data)
        return

    # ---- Phase 2: programming intent → ClarifierAgent 需求澄清 ----
    agent_input = AgentInput(
        task=text,
        context={
            "project": project_info,
            "history": history,
            "confirmed": {},
            "session_id": session_id,
            "project_name": project_name,
        },
        role=AgentRole.CLARIFIER,
    )
    agent = get_clarifier()
    output = await agent.execute(agent_input)

    # 后台异步刷新 CONTEXT.md——不阻塞聊天响应
    _schedule_context_sync(project_name)

    result_data = {
        "type": "clarify",
        "reply": output.result.get("reply", ""),
        "clarification_status": output.result.get("clarification_status", "clarifying"),
        "structured_prd": output.result.get("structured_prd"),
        "missing_fields": output.result.get("missing_fields", []),
        "agent_role": "Clarifier",
        # 携带 ChatterAgent 的意图识别结果——前端可展示过渡信息
        "chatter_notice": chatter_reply,
    }
    # 首轮带项目匹配结果
    if candidates:
        result_data["candidates"] = candidates

    # ---- ClarifierAgent 输出 ready 时，过 V1-V3 校验 ----
    prd_raw = output.result.get("structured_prd")
    if result_data["clarification_status"] == "ready" and prd_raw:
        validation = validate_prd(prd_raw)
        if not validation.passed:
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
            _session_registry.add_message(session_id=session_id, role="user", content=text)
            _session_registry.add_message(
                session_id=session_id,
                role="agent",
                content=result_data["reply"],
                candidates=candidates or None,
            )
            _session_registry.touch(session_id)
        except Exception:
            pass

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


# ── CONTEXT.md 自动同步 ──────────────────────────────────

# WHY 模块级缓存: 避免每次聊天消息都调 LLM 重生成。
# 每个项目每分钟最多检查一次目录结构变化。
_last_context_sync: dict[str, float] = {}
_CONTEXT_SYNC_INTERVAL = 300  # 5 分钟节流


def _schedule_context_sync(project_name: str) -> None:
    """如果项目已注册且超时，后台异步刷新 CONTEXT.md。

    节流 5 分钟——防止每次输入都触发 LLM 调用。
    """
    import time

    if not project_name:
        return

    now = time.time()
    last = _last_context_sync.get(project_name, 0)
    if now - last < _CONTEXT_SYNC_INTERVAL:
        return

    _last_context_sync[project_name] = now

    proj = _registry.get(project_name)
    if proj is None or not proj.local_path:
        return

    # 检查 brief 是否存在——不存在则跳过（等首次生成）
    from orbit.brief.checker import check_brief
    status = check_brief(proj.local_path)
    if not status.has_brief:
        return

    # 后台异步刷新
    import asyncio as _async

    _async.create_task(_refresh_context_bg(proj.local_path, project_name))


async def _refresh_context_bg(project_path: str, project_name: str) -> None:
    """后台任务——重新扫描目录结构并更新 CONTEXT.md。"""
    import structlog as _sl
    logger = _sl.get_logger("orbit.chat.context_sync")

    try:
        from orbit.brief.generator import BriefGenerator, analyze_directory
        from orbit.brief.storage import read_brief

        brief = read_brief(project_path)
        if brief is None:
            return

        # 只在目录结构变化时才调用 LLM
        analysis = analyze_directory(project_path)
        if analysis.file_count < 5:
            return  # 项目太小，不生成

        # 需要 LLM——在后台获取
        llm = None
        try:
            from orbit.api.main import _llm_glm5
            llm = _llm_glm5
        except Exception:
            pass

        if llm is None:
            return

        gen = BriefGenerator(llm)
        written = await gen.generate_all_context_md(project_path, brief, min_subdirs=2)
        if written:
            logger.info("context_auto_refreshed", project=project_name, files=len(written))
    except Exception:
        logger.exception("context_auto_refresh_failed", project=project_name)
