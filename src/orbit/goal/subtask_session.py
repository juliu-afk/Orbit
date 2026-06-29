"""SubTaskSession——单个子任务的独立执行会话。

每个 SubTaskSession:
- 独立 128K 上下文窗口——不与任何其他子任务共享消息历史
- 独立 git 分支——基于 base_ref 创建
- 独立 Worktree 隔离
- 走完完整流水线: PARSING→PLANNING→CODING→CRITIQUE→VERIFYING→DONE

ProcessGuard 在每次状态转换前检查——不可绕过。

WHY 独立 Session 非协程: 独立 LLM 消息历史 = 独立上下文窗口。
多 Task 并行 = 多 SubTaskSession 同时运行——真隔离。
"""

from __future__ import annotations

<<<<<<< HEAD
import asyncio
=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
import structlog
from typing import TYPE_CHECKING, Any

from orbit.api.schemas.task import TaskState
from orbit.goal.models import GoalSession, SubTaskResult
from orbit.goal.process_guard import (
    FULL_PIPELINE_TRANSITIONS,
    FAST_LANE_TRANSITIONS,
    TERMINAL_STATES,
    ProcessGuard,
)

if TYPE_CHECKING:
    from orbit.agents.factory import AgentFactory
    from orbit.checkpoint.manager import CheckpointManager
    from orbit.compression.budget import TokenBudgetTracker
    from orbit.compose.models import Task
    from orbit.worktree.manager import WorktreeManager

logger = structlog.get_logger("orbit.goal")


class SubTaskSession:
    """单个子任务的独立执行会话。

    对标: 正常 Orbit 单任务执行——但由 MetaOrchestrator 调度而非用户手动触发。

    Usage:
        session = SubTaskSession(
            task=task,
            base_ref="main",
            goal_context={"goal": "...", "constraints": [...]},
            agent_factory=factory,
            worktree_manager=wt_mgr,
        )
        result = await session.run_full_pipeline()
    """

    # P2-5: CRITIQUE_GATE 无对应 Agent——由 CritiqueAgent 外部处理
    STATE_ROLE_MAP: dict[TaskState, str] = {
        TaskState.IDLE: "clarifier",
        TaskState.PARSING: "clarifier",
        TaskState.PLANNING: "architect",
        TaskState.CODING: "developer",
        TaskState.VERIFYING: "reviewer",
    }

    def __init__(
        self,
        task: Task,
        base_ref: str,
        goal_context: dict[str, Any],
        goal: GoalSession,
        agent_factory: AgentFactory,
        worktree_manager: WorktreeManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        budget_tracker: TokenBudgetTracker | None = None,
        critique_agent: Any = None,   # CritiqueAgent——延迟导入避免循环
        verifier: Any = None,          # ExecutorVerifier
    ) -> None:
        self.task = task
        self.base_ref = base_ref
        self.goal_context = goal_context  # Ledger 层: 目标/约束/架构决策
        self.goal = goal
        self._agent_factory = agent_factory
        self._worktree = worktree_manager
        self._checkpoint = checkpoint_manager
        self._budget = budget_tracker
        self._critique = critique_agent
        self._verifier = verifier

        # 每个 SubTaskSession 有独立的 ProcessGuard
        self._guard = ProcessGuard(task_id=task.id, goal_id=goal.id)

        # 快车道判定——仅 ComplexityScorer 可授权
        self._fast_lane = False
        self._critique_attempts = 0
        self._MAX_CRITIQUE_RETRIES = 2

    # ── 公共 API ──────────────────────────────────────

    async def run_full_pipeline(self) -> SubTaskResult:
        """执行完整流水线——每个状态不可跳过。

        ProcessGuard 在每次状态转换前检查——代码级强制。

        Returns:
            SubTaskResult: 含 status/pr_id/merge_sha/tokens_used
        """
        state = TaskState.IDLE
        context: dict[str, Any] = {
            "task": self.task,
            "goal_context": self.goal_context,
            "artifacts": {},
        }

        # 创建隔离 Worktree + 分支（如果有 worktree manager）
        wt_record = None
        if self._worktree:
            try:
                wt_record = await self._worktree.create(
                    branch=f"goal/{self.goal.id}/{self.task.id}",
                    base_ref=self.base_ref,
                )
                context["worktree_path"] = wt_record.path
            except Exception as e:
                logger.warning(
                    "worktree_create_failed_fallback_inline",
                    task_id=self.task.id,
                    error=str(e),
                )

        try:
            while state not in TERMINAL_STATES:
                # ProcessGuard——代码级检查，不可绕过
                await self._guard.check(state, context)

                # 执行当前状态
                observation = await self._execute_state(state, context)
                context["artifacts"][state.value] = observation

                # 批判门禁（CODING 完成后）
                if state == TaskState.CODING and self._critique:
                    critique_passed = await self._critique_gate(context)
                    if not critique_passed:
                        self._critique_attempts += 1
                        if self._critique_attempts > self._MAX_CRITIQUE_RETRIES:
                            return SubTaskResult(
                                task_id=self.task.id,
                                status="critique_loop",
                                error=f"批判退回 {self._critique_attempts} 次——超过上限",
                            )
                        # 退回 CODING——不转换状态
                        context["critique_feedback"] = context.get("last_critique", {})
                        logger.info(
                            "critique_rejected_retry_coding",
                            task_id=self.task.id,
                            attempt=self._critique_attempts,
                        )
                        continue

                # 状态转换
                next_state = self._transition(state)
                await self._save_checkpoint(self.task.id, next_state, context)
                logger.info(
                    "subtask_state_transition",
                    task_id=self.task.id,
                    from_state=state.value,
                    to_state=next_state.value,
                )
                state = next_state

<<<<<<< HEAD
        except asyncio.CancelledError:
            raise
=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
        except Exception as e:
            logger.error(
                "subtask_pipeline_failed",
                task_id=self.task.id,
                state=state.value,
                error=str(e),
                exc_info=True,
            )
            return SubTaskResult(
                task_id=self.task.id,
                status="error",
                error=str(e),
                tokens_used=self._budget.current_usage if self._budget else 0,
            )
        finally:
            # 清理 Worktree
            if wt_record and self._worktree:
                try:
                    await self._worktree.cleanup(wt_record)
                except Exception:
                    pass

        return SubTaskResult(
            task_id=self.task.id,
            status="ok",
            tokens_used=self._budget.current_usage if self._budget else 0,
        )

    # ── 内部: 状态执行 ─────────────────────────────────

    async def _execute_state(
        self,
        state: TaskState,
        context: dict[str, Any],
    ) -> str:
        """执行单个状态——拉起对应 Agent 角色。

        WHY 独立方法: 方便子类/test mock。
        """
        role = self.STATE_ROLE_MAP.get(state, "developer")
        context["state"] = state.value
        context["agent_name"] = role

        agent_llm = None  # AgentFactory 内部路由模型
        try:
            agent = self._agent_factory.create(role, llm=agent_llm)
<<<<<<< HEAD
        except asyncio.CancelledError:
            raise
=======
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
        except Exception as e:
            logger.error("agent_create_failed", role=role, error=str(e))
            raise RuntimeError(f"Agent {role} 创建失败: {e}") from e

        # 构建输入——注入 Goal 上下文 + 当前状态
        from orbit.agents.base import AgentInput

        agent_input = AgentInput(
            task=context.get("task_description", str(self.task.description)),
            context={
                "goal": self.goal_context,
                "state": state.value,
                "artifacts": context.get("artifacts", {}),
                "critique_feedback": context.get("critique_feedback"),
            },
            role=role,
        )

        try:
            output = await agent.execute(agent_input)
            if output.status == "ok":
                result = output.result
                return (
                    result.get("design")
                    or result.get("code")
                    or result.get("review")
                    or str(result)
                )
            raise RuntimeError(f"Agent {role} 返回错误: {output.error}")
        except Exception as e:
            logger.error("agent_execute_failed", role=role, task_id=self.task.id, error=str(e))
            raise

    # ── 内部: 批判门禁 ─────────────────────────────────

    async def _critique_gate(self, context: dict[str, Any]) -> bool:
        """批判门禁——CODING 完成后，CritiqueAgent 审查。

        只有 APPROVED 才放行到 VERIFYING。

        WHY 门禁而非建议: Goal 模式无人工审查——CritiqueAgent 是品质底线。
        """
        if not self._critique:
            return True  # 无批判 Agent → 直接通过

        code_artifact = context.get("artifacts", {}).get(TaskState.CODING.value, "")
        try:
            result = await self._critique.critique(
                task=self.task,
                code_artifact=code_artifact,
                diff_only=True,
            )
            context["last_critique"] = {
                "approved": result.approved,
                "issues": result.issues,
                "severity": result.max_severity,
            }
            if not result.approved:
                logger.info(
                    "critique_not_approved",
                    task_id=self.task.id,
                    issue_count=len(result.issues),
                    max_severity=result.max_severity,
                )
            return result.approved
<<<<<<< HEAD
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("critique_failed_fail_open", error=str(e))
        except Exception as e:
=======
        except Exception as e:
            logger.warning("critique_failed_fail_open", error=str(e))
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
            return True  # 批判失败 → fail-open——不阻塞流程

    # ── 内部: 状态转换 ─────────────────────────────────

    def _transition(self, current: TaskState) -> TaskState:
        """执行状态转换——快车道模式走简化路径。"""
        if current in TERMINAL_STATES:
            raise ValueError(f"终态 {current.value} 不可转换")
        transitions = FAST_LANE_TRANSITIONS if self._fast_lane else FULL_PIPELINE_TRANSITIONS
        if current not in transitions:
            raise ValueError(f"状态 {current.value} 无定义的后继状态")
        return transitions[current]

    # ── 内部: 检查点 ───────────────────────────────────

    async def _save_checkpoint(
        self,
        task_id: str,
        state: TaskState,
        context: dict[str, Any],
    ) -> None:
        """保存检查点——每次状态转换后。"""
        if not self._checkpoint:
            return
        try:
            from orbit.checkpoint.manager import CheckpointData

            # 序列化——只保存可 JSON 化的数据
            safe_context = {
                "state": state.value,
                "task_id": task_id,
                "goal_id": self.goal.id,
                "artifacts_summary": {
                    k: str(v)[:500] for k, v in context.get("artifacts", {}).items()
                },
                "critique_attempts": self._critique_attempts,
            }
            data = CheckpointData(
                task_id=task_id,
                state=state.value,
                context=safe_context,
            )
            await self._checkpoint.save(task_id, data)
<<<<<<< HEAD
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("checkpoint_save_failed", task_id=task_id, error=str(e))
=======
        except Exception as e:
            logger.warning("checkpoint_save_failed", task_id=task_id, error=str(e))
>>>>>>> 1cdddeacb9fe2b301c27aaa7e82c7080c6549313
