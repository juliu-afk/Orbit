"""HITL (Human-in-the-Loop) 移交管理器——从零构建。

当前状态: meta_orchestrator.py:411 _present_for_confirmation() 总是返回 True
Phase A 目标: 建立真正的 HITL 机制——Monitor 检测到 CRITICAL → 暂停 Agent → 通知前端 → 等待响应

设计:
  - WebSocket 通知现有驾驶舱（HITLModal.vue）
  - 超时自动熔断（默认 5 分钟无人响应 → ABORT）
  - 响应选项: CONTINUE / ROLLBACK / ABORT / STEP_BACK
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.events.bus import EventBus

import structlog

logger = structlog.get_logger("orbit.metacognition.hitl")


class HITLAction(StrEnum):
    CONTINUE = "continue"    # 继续执行
    ROLLBACK = "rollback"    # 回滚到检查点
    ABORT = "abort"          # 终止任务
    STEP_BACK = "step_back"  # 退回一步，重新反思


@dataclass
class HITLRequest:
    """HITL 请求——从 Monitor 发往前端。"""
    alert_type: str
    severity: str
    message: str
    original_goal: str = ""
    current_state: str = ""
    suggested_action: HITLAction = HITLAction.STEP_BACK
    context: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: __import__("time").time())


# 全局注册表——WS router 通过 task_id 查找 HITLManager 实例
_hitl_registry: dict[str, "HITLManager"] = {}


def resolve_hitl_static(task_id: str, response: "HITLResponse") -> bool:
    """WS router 收到 hitl:response 后调用——查找注册的 HITLManager 并 resolve。"""
    hitl = _hitl_registry.get(task_id)
    if hitl:
        hitl.resolve(task_id, response)
        return True
    return False


@dataclass
class HITLResponse:
    """HITL 响应——从前端回传。"""
    action: HITLAction
    reason: str = ""
    target_checkpoint: str | None = None


class HITLManager:
    """HITL 移交管理器。

    用法:
        hitl = HITLManager(event_bus=bus)
        request = hitl.build_request(alert, agent_state)
        response = await hitl.wait_for_response(request, timeout=300)
        if response.action == HITLAction.ABORT:
            raise TaskAborted(...)
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        default_timeout: float = 300.0,  # 默认 5 分钟
    ) -> None:
        self._event_bus = event_bus
        self._default_timeout = default_timeout
        self._pending: dict[str, asyncio.Future[HITLResponse]] = {}

    def build_request(
        self,
        alert_type: str,
        severity: str,
        message: str,
        goal: str = "",
        state: str = "",
        suggested_action: HITLAction = HITLAction.STEP_BACK,
        context: dict | None = None,
    ) -> HITLRequest:
        """构建 HITL 请求。"""
        return HITLRequest(
            alert_type=alert_type,
            severity=severity,
            message=message,
            original_goal=goal,
            current_state=state,
            suggested_action=suggested_action,
            context=context or {},
        )

    async def request_intervention(
        self,
        task_id: str,
        request: HITLRequest,
        timeout: float | None = None,
    ) -> HITLResponse:
        """发送 HITL 请求到前端并等待响应。

        超时 → 自动熔断，返回 ABORT。
        """
        timeout = timeout or self._default_timeout

        # 通过 EventBus 推送 HITL 请求到 WebSocket
        # 注册到全局表——WS router 需要找到此实例
        _hitl_registry[task_id] = self

        if self._event_bus:
            try:
                from orbit.events.schemas import DashboardEvent
                self._event_bus.publish(DashboardEvent(
                    type="hitl:request",
                    task_id=task_id,
                    payload={
                        "alert_type": request.alert_type,
                        "severity": request.severity,
                        "message": request.message,
                        "goal": request.original_goal,
                        "state": request.current_state,
                        "suggested_action": request.suggested_action.value,
                        "context": request.context,
                    },
                ))
            except Exception:
                logger.debug("hitl_event_publish_failed", exc_info=True)

        # 创建 Future 等待响应
        loop = asyncio.get_event_loop()
        future: asyncio.Future[HITLResponse] = loop.create_future()
        self._pending[task_id] = future

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning("hitl_timeout_auto_abort", task_id=task_id, timeout=timeout)
            return HITLResponse(
                action=HITLAction.ABORT,
                reason=f"HITL 超时 ({timeout}s)，自动熔断",
            )
        finally:
            self._pending.pop(task_id, None)

    def resolve(self, task_id: str, response: HITLResponse) -> None:
        """从前端 WebSocket 收到用户响应后调用。"""
        future = self._pending.get(task_id)
        if future and not future.done():
            future.set_result(response)

    def abort_all(self, reason: str = "系统关闭") -> None:
        """终止所有等待中的 HITL 请求。"""
        for task_id, future in list(self._pending.items()):
            if not future.done():
                future.set_result(HITLResponse(action=HITLAction.ABORT, reason=reason))
        self._pending.clear()
