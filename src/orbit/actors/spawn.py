"""ActorSpawn——子Agent 创建与生命周期管理。

对标 MiMo Code actor/spawn.ts ~400行。
流程: allocate ID → register (pending) → fork fiber → Deferred result.

WHY DeferredActor: 父Agent 不需要等待子Agent 完成——
可后续查询结果，异步解耦。
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from orbit.actors.models import ActorOutcome, ActorRecord, ActorStatus
from orbit.agents.base import AgentInput, AgentRole
from orbit.stream.cancellation import CancellationToken

logger = structlog.get_logger()


class DeferredActor:
    """异步 Actor 结果句柄——对标 MiMo Deferred<AgentOutcome>.

    父Agent 可以:
    - await deferred.result() → 等待完成
    - deferred.actor_id → 查询状态
    - deferred.cancel() → 取消子Agent
    """

    def __init__(self, actor_id: str, task: asyncio.Task) -> None:
        self.actor_id = actor_id
        self._task = task
        self._token = CancellationToken()

    async def result(self, timeout: float | None = None) -> dict:
        """等待 Actor 完成，返回 result dict。"""
        try:
            return await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            self._token.cancel()
            return {"status": "timeout", "error": f"超时 ({timeout}s)"}

    def cancel(self) -> None:
        """取消子Agent 执行。"""
        self._token.cancel()
        if not self._task.done():
            self._task.cancel()

    @property
    def done(self) -> bool:
        return self._task.done()

    @property
    def token(self) -> CancellationToken:
        return self._token


class ActorSpawn:
    """子Agent 创建器——对标 MiMo Code spawn 服务。

    Usage:
        spawn = ActorSpawn(registry, agent_factory)
        deferred = await spawn.spawn(
            task="审查 auth.py 的安全性",
            role="reviewer",
            parent_task_id="task-001",
            tools=tool_registry,
            event_bus=None,
        )
        result = await deferred.result(timeout=300)
    """

    def __init__(self, registry: Any = None, agent_factory: Any = None) -> None:
        from orbit.actors.registry import ActorRegistry

        self.registry: ActorRegistry = registry or ActorRegistry()
        self.agent_factory = agent_factory  # AgentFactory

    async def spawn(
        self,
        task: str,
        role: str = "developer",
        parent_task_id: str = "",
        context: dict | None = None,
        llm: Any = None,
        tools: Any = None,
        event_bus: Any = None,
        background: bool = False,
    ) -> DeferredActor:
        """创建并启动子Agent。

        Args:
            task: 任务描述
            role: Agent 角色
            parent_task_id: 父任务 ID
            context: 额外上下文
            llm: LLMClient（None = 继承父Agent）
            tools: ToolRegistry（None = 继承父Agent）
            event_bus: EventBus（None = 不推送事件）
            background: True = 后台执行（不阻塞 spawn 调用）

        Returns:
            DeferredActor——异步结果句柄

        Raises:
            RuntimeError: 活跃 actor 超过并发上限
        """
        # 1. 并发限制检查
        if self.registry.count_active() >= ActorRecord.MAX_CONCURRENT:
            raise RuntimeError(
                f"并发子Agent 已达上限 ({ActorRecord.MAX_CONCURRENT})——请等待或取消现有 Actor"
            )

        # 2. 分配 actor ID
        actor_id = self.registry.allocate(parent_task_id)

        # 3. 创建 AgentRole
        try:
            agent_role = AgentRole(role)
        except ValueError:
            agent_role = AgentRole.DEVELOPER

        # 4. 注册 actor (pending)
        record = ActorRecord(
            actor_id=actor_id,
            parent_task_id=parent_task_id,
            role=role,
            task=task,
            status=ActorStatus.PENDING,
        )
        self.registry.register(record)

        # 5. 创建 Agent 实例
        agent = self._create_agent(agent_role, llm, tools, event_bus)

        # 6. 创建 cancel token
        token = CancellationToken()

        # 7. fork 执行 fiber
        input_data = AgentInput(
            task=task,
            context=context or {"task_id": parent_task_id},
            role=agent_role,
        )

        async def _run_actor() -> dict:
            """Actor 执行纤维——对标 MiMo runTurn Effect.uninterruptible."""
            self.registry.update_status(actor_id, ActorStatus.RUNNING)
            try:
                # 流式执行——收集最终结果
                output_text = ""
                turns = 0
                tool_calls_count = 0

                async for event in agent.execute_stream(input_data, cancel_token=token):
                    if event.type.value == "finish_step":
                        output_text = event.data.get("output", "")
                        turns = event.data.get("turns", 0)
                        tool_calls_count = event.data.get("tool_calls", 0)

                result = {
                    "output": output_text,
                    "turns": turns,
                    "tool_calls": tool_calls_count,
                    "status": "ok",
                }
                self.registry.update_status(
                    actor_id,
                    ActorStatus.IDLE,
                    outcome=ActorOutcome.SUCCESS,
                    result=result,
                )
                return result

            except asyncio.CancelledError:
                self.registry.update_status(
                    actor_id,
                    ActorStatus.IDLE,
                    outcome=ActorOutcome.CANCELLED,
                    error="actor cancelled",
                )
                return {"status": "cancelled", "error": "actor cancelled"}

            except Exception as e:
                logger.error("actor_failed", actor_id=actor_id, error=str(e))
                self.registry.update_status(
                    actor_id,
                    ActorStatus.IDLE,
                    outcome=ActorOutcome.FAILURE,
                    error=str(e),
                )
                return {"status": "error", "error": str(e)}

        if background:
            # 后台执行——Deferred 可后续查询
            coro = _run_actor()
            task_obj = asyncio.create_task(coro)
            return DeferredActor(actor_id, task_obj)
        else:
            # 前台执行——阻塞等待完成（用于顺序编排）
            result = await _run_actor()
            # 包装为已完成 Deferred
            async def _done():
                return result
            task_obj = asyncio.create_task(_done())
            await task_obj  # 确保完成
            deferred = DeferredActor(actor_id, task_obj)
            return deferred

    def _create_agent(
        self, role: AgentRole, llm: Any, tools: Any, event_bus: Any
    ) -> Any:
        """创建 Agent 实例——优先用 AgentFactory，回退直接实例化。"""
        if self.agent_factory:
            try:
                return self.agent_factory.create(
                    role=role,
                    llm=llm,
                    tools=tools,
                    event_bus=event_bus,
                )
            except Exception as e:
                logger.warning("factory_create_failed", error=str(e))

        # 回退——直接创建 ReActAgent
        from orbit.agents.react_agent import ReActAgent

        class SpawnedAgent(ReActAgent):
            pass

        SpawnedAgent.role = role  # type: ignore[attr-defined]
        return SpawnedAgent(llm=llm, tools=tools, event_bus=event_bus)
