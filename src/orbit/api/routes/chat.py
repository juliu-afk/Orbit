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
from orbit.api.dependencies import _verify_token  # P1-3: JWT + static token
from orbit.core.config import settings
from orbit.core.context import get_context, set_context
from orbit.projects.registry import ProjectRegistry
from orbit.sessions.registry import SessionRegistry
from orbit.skills.models import ChatMode
from orbit.skills.registry import get_skill_registry

import structlog as _structlog

logger = _structlog.get_logger("orbit.chat")

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
    # P0-1: WS 认证——accept 前校验 token
    # WHY gated on AUTH_ENABLED: 桌面应用默认不启用认证（无 ORBIT_AUTH_TOKEN 环境变量），
    #   仅生产部署（env var 已设）时强制校验，与 AuthMiddleware 行为一致
    if settings.AUTH_ENABLED:
        token = ws.query_params.get("token", "")
        # P1-3: 静态 token + JWT 双模式验证
        if not _verify_token(token):
            await ws.close(code=4001, reason="未授权访问")
            return

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
            # ChatMode: 从 WebSocket 读取模式，默认 Auto Mode（向后兼容）
            mode_raw = payload.get("mode", "Auto Mode")
            try:
                chat_mode = ChatMode(mode_raw)
            except ValueError:
                chat_mode = ChatMode.AUTO

            if msg_type == "chat":
                await _handle_chat(ws, text, session_id, project_name, payload, chat_mode)
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
        logger.error(
            "goal_background_failed", goal_id=goal_id, exc_info=True
        )


async def _handle_watch_command(ws: WebSocket, text: str) -> None:
    """/watch <url或路径> [问题] —— 下载视频 → 抽帧 → 多模态分析。"""
    # 解析参数: /watch <url> [问题]
    parts = text[6:].strip()  # 去掉 "/watch"
    if not parts:
        await _send(ws, 1, None, "用法: /watch <视频URL或本地路径> [问题]")
        return

    # 分离 URL 和可选问题
    tokens = parts.split(maxsplit=1)
    url = tokens[0].strip()
    question = tokens[1].strip() if len(tokens) > 1 else "请总结这个视频的内容"

    await _send(ws, 0, {"type": "watch_start", "url": url[:120]}, "正在分析视频...")

    try:
        from orbit.tools.video_tools import watch_video

        result = await watch_video(url=url, question=question)
        await _send(
            ws,
            0,
            {
                "type": "watch_result",
                "url": url[:120],
                "analysis": result.get("analysis", ""),
                "frames_count": result.get("frames_count", 0),
                "captions_available": result.get("captions_available", False),
                "model": result.get("model", ""),
                "cost_usd": result.get("cost_usd", 0),
            },
        )
    except Exception as e:
        logger.warning("watch_command_failed", url=url[:120], error=str(e))
        await _send(ws, 1, None, f"视频分析失败: {e}")


async def _handle_ocr_command(ws: WebSocket, text: str) -> None:
    """/ocr <文件路径> —— OCR 图片/PDF → Markdown。"""
    file_path = text[4:].strip()  # 去掉 "/ocr"
    if not file_path:
        await _send(ws, 1, None, "用法: /ocr <文件路径>")
        return

    # 去掉可能的外层引号
    file_path = file_path.strip().strip('"').strip("'")

    await _send(ws, 0, {"type": "ocr_start", "file": file_path}, "正在 OCR...")

    try:
        from orbit.tools.ocr_tools import ocr_document

        result = await ocr_document(file_path)
        await _send(
            ws,
            0,
            {
                "type": "ocr_result",
                "file": file_path,
                "text": result.get("text", ""),
                "pages": result.get("pages", 0),
                "tokens": result.get("tokens", 0),
                "cost_usd": result.get("cost_usd", 0),
            },
        )
    except FileNotFoundError:
        await _send(ws, 1, None, f"文件不存在: {file_path}")
    except Exception as e:
        logger.warning("ocr_command_failed", file=file_path, error=str(e))
        await _send(ws, 1, None, f"OCR 失败: {e}")


async def _handle_parse_command(ws: WebSocket, text: str) -> None:
    """/parse <文件路径> —— 解析 PDF/Word/Excel/PPT/文本 → Markdown。"""
    file_path = text[6:].strip()  # 去掉 "/parse"
    if not file_path:
        await _send(ws, 1, None, "用法: /parse <文件路径>")
        return

    # 去掉可能的外层引号
    file_path = file_path.strip().strip('"').strip("'")

    await _send(ws, 0, {"type": "parse_start", "file": file_path}, "正在解析文档...")

    try:
        from orbit.tools.file_parser import file_parser

        result = await file_parser(file_path)
        await _send(
            ws,
            0,
            {
                "type": "parse_result",
                "file": file_path,
                "text": result.get("text", ""),
                "pages": result.get("pages", 0),
                "file_type": result.get("file_type", ""),
            },
        )
    except FileNotFoundError:
        await _send(ws, 1, None, f"文件不存在: {file_path}")
    except Exception as e:
        logger.warning("parse_command_failed", file=file_path, error=str(e))
        await _send(ws, 1, None, f"文档解析失败: {e}")


async def _handle_chat(
    ws: WebSocket,
    text: str,
    session_id: str,
    project_name: str,
    payload: dict[str, Any],
    chat_mode: ChatMode = ChatMode.AUTO,
) -> None:
    """处理用户聊天消息：ChatterAgent 首触 → 意图路由 → Skill/Chain/Clarifier。

    数据流:
        Phase 0: /slash → SkillRegistry 精确匹配
        Phase 1: ChatterAgent → chat/skill/chain/programming 四分类
          - chat → 直接回复
          - skill → SkillExecutor（单 Skill）
          - chain → ComposeOrchestrator（多步编排）
          - programming → ClarifierAgent（需求澄清）
    """
    if not text.strip():
        await _send(ws, 1, None, "输入为空")
        return

    # 注入 ChatMode 到执行上下文——ToolRegistry 工具门禁会读取
    set_context(chat_mode=chat_mode, session_id=session_id)

    # ---- Phase 0: /slash 命令路由（SkillRegistry 动态匹配）----
    if text.strip().startswith("/"):
        # 保留已有硬编码命令（向后兼容）
        if text.strip().startswith("/goal"):
            await _handle_goal_command(ws, text.strip())
            return
        if text.strip().startswith("/watch"):
            await _handle_watch_command(ws, text.strip())
            return
        if text.strip().startswith("/ocr"):
            await _handle_ocr_command(ws, text.strip())
            return
        if text.strip().startswith("/parse"):
            await _handle_parse_command(ws, text.strip())
            return

        # NEW: SkillRegistry 动态匹配——新增 Skill 无需改此处代码
        slash_name = text.strip().split()[0].lstrip("/")  # "/review" → "review"
        skill_registry = get_skill_registry()
        skill = skill_registry.find_by_slash(slash_name)
        if skill is not None:
            logger.info("skill_slash_match", name=skill.name)
            await _execute_skill(ws, skill, text, session_id, chat_mode)
            return
        # 不是已知命令也不是已知 Skill → 当作普通文本继续 Phase 1

    # 保留: /mode 命令（ModeTuner 检测）——保持 /mode 不匹配 skill
    if text.strip().startswith("/mode"):
        # /mode 由 ChatterAgent 内置的 ModeTuner 处理
        pass

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
    skill_name = chatter_output.result.get("skill_name", "")
    skill_confidence = chatter_output.result.get("confidence", 0.0)
    chain_skills = chatter_output.result.get("skills", [])

    # ---- Phase 1 路由：chat | skill | chain | programming ----
    # WHY 四分类: skill/chain 直接执行，chat 回复，programming 走 ClarifierAgent

    if intent == "skill" and skill_name:
        # 自然语言匹配到 Skill
        skill_registry = get_skill_registry()
        skill = skill_registry.get(skill_name)
        if skill is not None:
            # 阈值判断
            if skill_confidence >= 0.7:
                # 直接触发
                logger.info("skill_auto_trigger", name=skill_name, confidence=skill_confidence)
                await _send(ws, 0, {
                    "type": "chat",
                    "reply": f"🔧 启动技能「{skill.description}」...",
                    "agent_role": "Chatter",
                })
                await _execute_skill(ws, skill, text, session_id, chat_mode)
                return
            elif skill_confidence >= 0.4:
                # 提示确认——由前端弹确认框（当前版本简化：告知用户后触发）
                logger.info("skill_confirm_needed", name=skill_name, confidence=skill_confidence)
                await _send(ws, 0, {
                    "type": "chat",
                    "reply": f"📎 检测到意图「{skill.description}」，置信度 {int(skill_confidence*100)}%。如需执行请确认。",
                    "agent_role": "Chatter",
                    "pending_skill": skill_name,
                    "pending_confidence": skill_confidence,
                })
                # 暂不自动执行——等待用户确认后由前端发 confirm_skill
                _session_registry.add_message(session_id=session_id, role="user", content=text)
                return
            # else: < 0.4 → 当作普通 chat

    if intent == "chain" and chain_skills:
        # 多步编排 → ComposeOrchestrator
        logger.info("chain_trigger", skills=chain_skills)
        await _send(ws, 0, {
            "type": "chat",
            "reply": f"🔗 启动编排链: {' → '.join(chain_skills)}...",
            "agent_role": "Chatter",
        })
        await _execute_chain(ws, chain_skills, text, session_id, chat_mode)
        return

    if intent == "chat" or (intent not in ("programming", "skill", "chain")):
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
    _schedule_context_sync(project_name, _registry)

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
        from orbit.api.main import _scheduler
        from orbit.api.routes.tasks import create_task_record

        # PR3: 建任务记录 + IDLE 检查点，再 spawn_task 真实后台调度（可 cancel）
        task_id = await create_task_record(
            _scheduler, prd_text[:5000], session_id=session_id or "", project_name=project_name or ""
        )

        try:
            if _scheduler is not None:
                _scheduler.spawn_task(task_id, prd_text[:5000])
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


# ── Skill 执行 ──────────────────────────────────────


async def _execute_skill(
    ws: WebSocket,
    skill: object,  # ChatSkill
    user_text: str,
    session_id: str,
    chat_mode: ChatMode,
) -> None:
    """执行单个 Skill——创建 Agent 并注入 Skill body 作 system_prompt。

    WHY 独立函数: 单 Skill 和 chain 中每步共用此逻辑。
    """
    from orbit.agents.factory import AgentFactory
    from orbit.agents.base import AgentInput, AgentRole

    try:
        # 解析 AgentRole——skill.agent_role 来自 SKILL.md，可能无效
        role_str = skill.agent_role if hasattr(skill, "agent_role") else "developer"
        try:
            agent_role = AgentRole(role_str)
        except ValueError:
            agent_role = AgentRole.DEVELOPER

        agent_input = AgentInput(
            task=user_text,
            context={
                "skill_name": skill.name,
                "skill_body": skill.body,
                "chat_mode": chat_mode.value,
                "session_id": session_id,
            },
            role=agent_role,
        )

        agent = AgentFactory.create(agent_role)
        # 注入 Skill body 到 agent——Agent 的 system_prompt 会拼接 skill body
        if hasattr(agent, "_skill_body"):
            agent._skill_body = skill.body  # type: ignore[attr-defined]

        output = await agent.execute(agent_input)
        reply = output.result.get("reply", str(output.result)[:2000])

        await _send(ws, 0, {
            "type": "chat",
            "reply": reply,
            "agent_role": skill.agent_role if hasattr(skill, "agent_role") else "Developer",
            "skill_name": skill.name,
        })
    except Exception as e:
        logger.error("skill_execute_failed", name=skill.name, error=str(e))
        await _send(ws, 1, None, f"Skill {skill.name} 执行失败: {e}")


async def _execute_chain(
    ws: WebSocket,
    skill_names: list[str],
    user_text: str,
    session_id: str,
    chat_mode: ChatMode,
) -> None:
    """执行 Skill 编排链——调 ComposeOrchestrator.run_skill_chain()。

    WHY 独立函数: ComposeOrchestrator 需要独立的进度回调通道。
    """
    skill_registry = get_skill_registry()
    try:
        chain = skill_registry.build_chain(skill_names)
    except FileNotFoundError as e:
        await _send(ws, 1, None, str(e))
        return

    # 流式进度回调——每个阶段完成时推送到聊天框
    async def progress_callback(phase: str, status: str, message: str) -> None:
        await _send(ws, 0, {
            "type": "compose_progress",
            "phase": phase,
            "status": status,
            "message": message,
        })

    # 尝试通过 ComposeOrchestrator 执行
    import importlib
    try:
        from orbit.api.main import app as _app
        orch = getattr(_app.state, "compose_orchestrator", None)
        if orch and hasattr(orch, "run_skill_chain"):
            result = await orch.run_skill_chain(
                skills=[s.name for s in chain],
                user_input=user_text,
                stream_callback=progress_callback,
            )
            await _send(ws, 0, {
                "type": "chat",
                "reply": f"编排链完成: {' → '.join(skill_names)}",
                "agent_role": "Orchestrator",
                "compose_result": str(result)[:2000] if result else "",
            })
            return
    except Exception as e:
        logger.warning("compose_chain_fallback", error=str(e))

    # 降级：逐个执行 Skill
    for skill in chain:
        await progress_callback(skill.phase, "running", f"执行 {skill.name}...")
        await _execute_skill(ws, skill, user_text, session_id, chat_mode)
        await progress_callback(skill.phase, "done", f"{skill.name} 完成")

    await _send(ws, 0, {
        "type": "chat",
        "reply": f"编排链执行完毕: {' → '.join(skill_names)}",
        "agent_role": "Orchestrator",
    })


# ── CONTEXT.md 自动同步 ──────────────────────────────────

# WHY 模块级缓存: 避免每次聊天消息都调 LLM 重生成。
# 每个项目每分钟最多检查一次目录结构变化。
_last_context_sync: dict[str, float] = {}
from orbit.api.routes.chat_context import _schedule_context_sync
