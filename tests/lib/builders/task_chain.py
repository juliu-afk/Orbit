"""TaskChain——完整 Task 生命周期构建器。

模拟调度器状态机 IDLE→PARSING→PLANNING→CODING→VERIFYING→DONE。
内部编排真实 Agent 逻辑（AgentFactory + Agent.execute），
但 LLM 调用和沙箱执行由 Mock 替代。

使用示例:
    chain = TaskChain()
    result = await chain.start("实现登录功能").run_to_completion()
    chain.assert_done()
    chain.assert_checkpoints_saved(4)
"""

from __future__ import annotations

from typing import Any

import structlog

from orbit.agents.base import AgentInput, AgentOutput, AgentRole
from tests.lib.factories.agent import create_agent_output
from tests.lib.factories.prd import create_prd
from tests.lib.mocks.llm_client import MockLLMClient
from tests.lib.mocks.sandbox import MockSandbox
from tests.lib.mocks.checkpoint import MockCheckpointManager
from tests.lib.mocks.circuit_breaker import MockCircuitBreaker
from tests.lib.mocks.event_bus import MockEventBus
from tests.lib.mocks.tool_registry import MockToolRegistry

logger = structlog.get_logger()

# 状态机——与生产 scheduler/task_runner.py:39-45 一致
ROLE_MAP = {
    "IDLE": "clarifier",
    "PARSING": "clarifier",
    "PLANNING": "architect",
    "CODING": "developer",
    "VERIFYING": "reviewer",
}

# 标准状态转换序列
STANDARD_STATES = ["IDLE", "PARSING", "PLANNING", "CODING", "VERIFYING", "DONE"]
FAST_LANE_STATES = ["IDLE", "PARSING", "CODING", "DONE"]

TERMINAL_STATES = {"DONE", "FAILED", "CANCELLED"}


class TaskChain:
    """完整 Task 生命周期构建器。

    链式 API 风格，每步可覆盖默认 Mock。
    """

    def __init__(self, mocks: dict[str, Any] | None = None, task_id: str | None = None) -> None:
        """初始化 TaskChain。

        Args:
            mocks: Mock 组件字典
            task_id: 任务 ID（None=自动生成）。避免并发测试 ID 碰撞。
        """
        import uuid
        mocks = mocks or {}
        self.task_id: str = task_id or uuid.uuid4().hex[:12]

        self.llm: MockLLMClient = mocks.get("llm", MockLLMClient())
        self.sandbox: MockSandbox = mocks.get("sandbox", MockSandbox())
        self.checkpoint: MockCheckpointManager = mocks.get("checkpoint", MockCheckpointManager())
        self.circuit_breaker: MockCircuitBreaker = mocks.get("circuit_breaker", MockCircuitBreaker())
        self.event_bus: MockEventBus = mocks.get("event_bus", MockEventBus())
        self.tool_registry: MockToolRegistry = mocks.get("tool_registry", MockToolRegistry())

        # 配置
        self._prd: str | None = None
        self._fast_lane: bool = False
        self._skip_clarification: bool = False
        self._fail_at: dict[str, str] = {}  # state → error message
        self._custom_results: dict[str, AgentOutput] = {}  # state → AgentOutput

        # 运行结果
        self._result: AgentOutput | None = None
        self.state_history: list[str] = []
        self.checkpoints: list[dict[str, Any]] = []
        self.final_state: str = ""

    # ── 链式配置方法 ──────────────────────────────────────

    def start(self, prd: str | None = None) -> "TaskChain":
        """设置 PRD 并开始构建。

        Args:
            prd: 任务 PRD 文本（None→使用默认中文 PRD）
        """
        self._prd = prd or create_prd()
        return self

    def with_llm(self, llm: MockLLMClient) -> "TaskChain":
        """注入自定义 MockLLMClient。"""
        self.llm = llm
        return self

    def with_sandbox(self, sandbox: MockSandbox) -> "TaskChain":
        """注入自定义 MockSandbox。"""
        self.sandbox = sandbox
        return self

    def with_checkpoint(self, checkpoint: MockCheckpointManager) -> "TaskChain":
        """注入自定义 MockCheckpointManager。"""
        self.checkpoint = checkpoint
        return self

    def with_event_bus(self, bus: MockEventBus) -> "TaskChain":
        """注入自定义 MockEventBus。"""
        self.event_bus = bus
        return self

    def with_tool_registry(self, registry: MockToolRegistry) -> "TaskChain":
        """注入自定义 MockToolRegistry。"""
        self.tool_registry = registry
        return self

    def fast_lane(self) -> "TaskChain":
        """使用快车道模式：IDLE→PARSING→CODING→DONE。"""
        self._fast_lane = True
        return self

    def skip_clarification(self) -> "TaskChain":
        """跳过 PARSING 阶段（直接进入 PLANNING）。"""
        self._skip_clarification = True
        return self

    def fail_at(self, state: str, error: str = "mock error") -> "TaskChain":
        """在指定状态触发失败。

        Args:
            state: 目标失败状态（IDLE/PARSING/PLANNING/CODING/VERIFYING）
            error: 错误消息
        """
        self._fail_at[state] = error
        return self

    def with_result_at(self, state: str, result: AgentOutput) -> "TaskChain":
        """为特定状态设置自定义 AgentOutput。

        Args:
            state: 目标状态
            result: 预设的 AgentOutput
        """
        self._custom_results[state] = result
        return self

    # ── 执行方法 ──────────────────────────────────────────

    async def run_to_completion(self) -> AgentOutput:
        """执行完整状态机直到终态。

        Returns:
            最终 AgentOutput

        Raises:
            ValueError: 未调用 start()
        """
        if self._prd is None:
            raise ValueError("must call start(prd) before run_to_completion()")

        return await self._run_state_machine()

    async def run_to_state(self, target_state: str) -> AgentOutput:
        """执行到指定状态。

        Args:
            target_state: 目标状态（不可为终态）

        Returns:
            该状态的 AgentOutput
        """
        if target_state in TERMINAL_STATES:
            raise ValueError(f"Cannot run to terminal state '{target_state}'")
        if self._prd is None:
            raise ValueError("must call start(prd) before run_to_state()")

        return await self._run_state_machine(target_state)

    async def _run_state_machine(self, stop_state: str | None = None) -> AgentOutput:
        """内部状态机循环。

        模拟 TaskRunner.run_task() 的核心循环：
        1. 确定当前状态
        2. 查找对应 Agent 角色
        3. 调用 Mock LLM（模拟 Agent 执行）
        4. 状态转换 → 保存检查点 → 发布事件
        """
        states = FAST_LANE_STATES if self._fast_lane else STANDARD_STATES
        current_idx = 0
        last_output = create_agent_output()

        while current_idx < len(states):
            state = states[current_idx]

            # 检查是否失败
            if state in self._fail_at:
                self.state_history.append(state)
                last_output = AgentOutput(status="error", result={}, error=self._fail_at[state])
                self._save_checkpoint(state, last_output, error=self._fail_at[state])
                self.final_state = "FAILED"
                self._result = last_output
                return last_output

            # 跳转澄清阶段（skip_clarification 时跳过 PARSING）
            if self._skip_clarification and state == "PARSING":
                current_idx += 1
                continue

            self.state_history.append(state)

            # 终态检查
            if state == "DONE":
                self._save_checkpoint(state, last_output)
                self.final_state = "DONE"
                self._result = last_output
                return last_output

            # 使用预设结果或模拟 Agent 执行
            if state in self._custom_results:
                last_output = self._custom_results[state]
            else:
                last_output = await self._simulate_agent_cycle(state)

            # 错误处理
            if last_output.status == "error":
                self._save_checkpoint(state, last_output, error=last_output.error)
                self.final_state = "FAILED"
                self._result = last_output
                return last_output

            # 保存检查点
            self._save_checkpoint(state, last_output)

            # 发布事件
            self.event_bus.publish({
                "type": "task:update",
                "task_id": "mock-task-id",
                "state": state,
                "status": last_output.status,
            })

            # 到达停止状态
            if stop_state is not None and state == stop_state:
                self.final_state = state
                self._result = last_output
                return last_output

            current_idx += 1

        self._result = last_output
        return last_output

    async def _simulate_agent_cycle(self, state: str) -> AgentOutput:
        """模拟 Agent 执行周期。

        调用 MockLLMClient.generate()（带 agent role context），
        然后模拟工具调度（通过 MockToolRegistry）。
        """
        role = ROLE_MAP.get(state, "developer")
        agent_input = AgentInput(
            task=self._prd or "test",
            context={"state": state, "mode": "fast" if self._fast_lane else "standard"},
            role=AgentRole(role),
        )

        try:
            # 模拟 LLM 调用
            from tests.lib.factories.llm import create_llm_request

            req = create_llm_request(
                prompt=f"[{role}] {self._prd}",
                messages=[{"role": "system", "content": f"你是 {role} Agent"}],
            )
            llm_resp = await self.llm.generate(req, task_id="mock-task-id", agent_name=role)

            # 如果有工具调用，模拟执行
            tool_call_count = 0
            if llm_resp.tool_calls:
                for tc in llm_resp.tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})
                    await self.tool_registry.dispatch(tool_name, tool_args, agent_name=role)
                    tool_call_count += 1

            return AgentOutput(
                status="ok",
                result={
                    "output": llm_resp.content,
                    "state": state,
                    "role": role,
                    "turns": 1 + tool_call_count,
                    "tool_calls": tool_call_count,
                },
            )
        except Exception as e:
            return AgentOutput(status="error", result={}, error=str(e))

    def _save_checkpoint(
        self,
        state: str,
        output: AgentOutput,
        error: str | None = None,
    ) -> None:
        """记录检查点（内存追踪 + MockCheckpointManager 同步更新）。

        WHY 同步更新: 场景测试通过 checkpoint_count 断言，Mock 无真实 I/O，
        直接更新 _store 供测试断言。
        """
        cp = {
            "state": state,
            "status": output.status,
            "output": output.result.get("output", "")[:200] if output.result else "",
            "error": error,
            "turns": output.result.get("turns", 0) if output.result else 0,
            "tool_calls": output.result.get("tool_calls", 0) if output.result else 0,
        }
        self.checkpoints.append(cp)

        from tests.lib.factories.checkpoint import create_checkpoint as _create_ck
        ck_data = _create_ck(state=state, context={"output": cp["output"], "error": error})
        self.checkpoint._store[f"{self.task_id}:{state}"] = ck_data

    # ── 断言方法 ──────────────────────────────────────────

    def assert_done(self) -> None:
        """断言任务成功完成。"""
        assert self.final_state == "DONE", (
            f"Expected DONE, got {self.final_state}. State history: {self.state_history}"
        )
        assert self._result is not None, "No result produced"
        assert self._result.status == "ok", f"Expected status='ok', got '{self._result.status}'"

    def assert_state(self, expected: str) -> None:
        """断言当前/最终状态。"""
        assert self.final_state == expected, (
            f"Expected state '{expected}', got '{self.final_state}'"
        )

    def assert_checkpoints_saved(self, count: int) -> None:
        """断言检查点保存数量。"""
        actual = len(self.checkpoints)
        assert actual == count, (
            f"Expected {count} checkpoints, got {actual}. Checkpoints: {self.checkpoints}"
        )

    def assert_failed_at(self, state: str) -> None:
        """断言在指定状态失败。"""
        assert self.final_state == "FAILED", (
            f"Expected FAILED, got {self.final_state}"
        )
        failed_checkpoint = [c for c in self.checkpoints if c.get("error")]
        assert len(failed_checkpoint) > 0, "No failed checkpoint found"
        assert failed_checkpoint[-1]["state"] == state, (
            f"Expected failure at '{state}', got '{failed_checkpoint[-1]['state']}'"
        )

    def assert_state_sequence(self, *expected_states: str) -> None:
        """断言状态转换序列。"""
        # 只比较非尾部的状态序列（最后可能有重复的 DONE/FAILED）
        history = self.state_history
        expected = list(expected_states)
        # 检查 expected 是否是 history 的子序列（按顺序）
        ei = 0
        for actual_state in history:
            if ei < len(expected) and actual_state == expected[ei]:
                ei += 1
        assert ei == len(expected), (
            f"Expected state sequence {expected} not found in history {history}"
        )

    # ── 重置 ──────────────────────────────────────────────

    def reset(self) -> None:
        """重置所有状态，准备下一次运行。"""
        self._prd = None
        self._fast_lane = False
        self._skip_clarification = False
        self._fail_at.clear()
        self._custom_results.clear()
        self._result = None
        self.state_history.clear()
        self.checkpoints.clear()
        self.final_state = ""
        self.llm.reset()
        self.sandbox.reset()
        self.checkpoint.reset()
        self.circuit_breaker.reset()
        self.event_bus.reset()
        self.tool_registry.reset()
