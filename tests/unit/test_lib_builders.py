"""测试库自身测试——builders/ 模块。

验证 TaskChain/DagChain/GoalChain/ChatChain 构建器的核心行为。
"""

from __future__ import annotations

import pytest

from tests.lib.assertions.task import assert_state_transition
from tests.lib.builders import ChatChain, DagChain, GoalChain, TaskChain
from tests.lib.mocks import MockLLMClient


# ── TaskChain ───────────────────────────────────────────

class TestTaskChain:
    @pytest.mark.asyncio
    async def test_normal_flow(self):
        chain = TaskChain()
        result = await chain.start("实现登录").run_to_completion()
        chain.assert_done()
        assert result.status == "ok"
        assert len(chain.state_history) >= 5

    @pytest.mark.asyncio
    async def test_fast_lane(self):
        chain = TaskChain()
        await chain.start("fix typo").fast_lane().run_to_completion()
        chain.assert_done()
        assert "PLANNING" not in chain.state_history
        assert "VERIFYING" not in chain.state_history

    @pytest.mark.asyncio
    async def test_fail_at(self):
        chain = TaskChain()
        result = await chain.start("bad task").fail_at("CODING", "syntax error").run_to_completion()
        assert result.status == "error"
        chain.assert_failed_at("CODING")

    @pytest.mark.asyncio
    async def test_skip_clarification(self):
        chain = TaskChain()
        await chain.start("task").skip_clarification().run_to_completion()
        chain.assert_done()
        assert "PARSING" not in chain.state_history

    @pytest.mark.asyncio
    async def test_must_call_start(self):
        chain = TaskChain()
        with pytest.raises(ValueError, match="must call start"):
            await chain.run_to_completion()

    @pytest.mark.asyncio
    async def test_task_id_parameterized(self):
        chain = TaskChain(task_id="custom-id-123")
        await chain.start("task").run_to_completion()
        assert chain.task_id == "custom-id-123"

    @pytest.mark.asyncio
    async def test_state_assertions(self):
        chain = TaskChain()
        await chain.start("task").run_to_completion()
        assert_state_transition(chain.state_history, "IDLE", "PARSING")
        assert_state_transition(chain.state_history, "VERIFYING", "DONE")

    @pytest.mark.asyncio
    async def test_checkpoints_saved(self):
        chain = TaskChain()
        await chain.start("task").run_to_completion()
        chain.assert_checkpoints_saved(6)  # IDLE→...→DONE = 6

    @pytest.mark.asyncio
    async def test_reset(self):
        chain = TaskChain()
        await chain.start("task").run_to_completion()
        chain.reset()
        assert chain._prd is None
        assert chain.final_state == ""
        assert chain.state_history == []


# ── DagChain ────────────────────────────────────────────

class TestDagChain:
    @pytest.mark.asyncio
    async def test_simple_dag(self):
        chain = DagChain()
        await chain.with_nodes(3).run()
        chain.assert_node_order()
        assert len(chain.results) == 3

    @pytest.mark.asyncio
    async def test_dag_with_dependencies(self):
        chain = DagChain()
        await chain.with_nodes(5).with_dependencies({2: [1], 3: [1], 4: [2, 3], 5: [4]}).run()
        chain.assert_node_order()
        # 分层: [[1], [2,3], [4], [5]] = 4 层
        assert len(chain.layers) >= 3

    @pytest.mark.asyncio
    async def test_layer_concurrency(self):
        chain = DagChain()
        # 无依赖→所有节点同层
        await chain.with_nodes(4).run()
        chain.assert_layer_concurrency()
        assert len(chain.layers) == 1
        assert len(chain.layers[0]) == 4

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        chain = DagChain()
        with pytest.raises(ValueError, match="循环依赖"):
            chain.with_nodes(3).with_dependencies({1: [3], 2: [1], 3: [2]})

    @pytest.mark.asyncio
    async def test_preset_node_failure(self):
        chain = DagChain()
        chain._node_results["node_2"] = {"status": "failed", "output": "boom"}
        chain._node_results["node_1"] = {"status": "ok", "output": "done"}
        await chain.with_nodes(3).with_dependencies({2: [1], 3: [2]}).run()
        chain.assert_node_failed("node_2")
        chain.assert_node_skipped("node_3")

    @pytest.mark.asyncio
    async def test_no_nodes_raises(self):
        chain = DagChain()
        with pytest.raises(ValueError, match="No nodes"):
            await chain.run()


# ── GoalChain ───────────────────────────────────────────

class TestGoalChain:
    @pytest.mark.asyncio
    async def test_full_chain(self):
        chain = GoalChain()
        result = await chain.intake("实现多租户RBAC").decompose().execute().critique().run()
        assert result["status"] == "ok"
        assert result["merged"] is True
        chain.assert_merged()

    @pytest.mark.asyncio
    async def test_needs_clarify_for_short_goal(self):
        chain = GoalChain()
        chain.intake("登录")
        assert chain.intake_result["needs_clarify"] is True

    @pytest.mark.asyncio
    async def test_no_clarify_for_detailed_goal(self):
        chain = GoalChain()
        chain.intake("实现功能，验收标准：1.支持JWT 2.bcrypt哈希")
        assert chain.intake_result["needs_clarify"] is False

    @pytest.mark.asyncio
    async def test_critique_failure(self):
        chain = GoalChain()
        result = await chain.intake("task").decompose().execute().critique(pass_critique=False).run()
        assert result["merged"] is False
        assert len(result["issues"]) > 0

    @pytest.mark.asyncio
    async def test_budget_check(self):
        chain = GoalChain()
        await chain.intake("task").decompose(["task1", "task2"]).execute().run()
        chain.assert_budget_not_exceeded()

    @pytest.mark.asyncio
    async def test_must_call_intake(self):
        chain = GoalChain()
        with pytest.raises(ValueError, match="must call intake"):
            await chain.run()


# ── ChatChain ───────────────────────────────────────────

class TestChatChain:
    @pytest.mark.asyncio
    async def test_dialog_creates_task(self):
        chain = ChatChain()
        result = await chain.dialog([
            {"role": "user", "content": "帮我实现登录功能，用JWT，bcrypt哈希"},
        ]).confirm_task_creation().run()
        chain.assert_task_created()
        assert result["task_created"] is True

    @pytest.mark.asyncio
    async def test_multi_turn_triggers_clarification(self):
        chain = ChatChain()
        result = await chain.dialog([
            {"role": "user", "content": "实现功能"},
            {"role": "assistant", "content": "请描述更多细节"},
            {"role": "user", "content": "登录功能"},
        ]).run()
        assert result["clarification_asked"] is True

    @pytest.mark.asyncio
    async def test_must_call_dialog(self):
        chain = ChatChain()
        with pytest.raises(ValueError, match="must call dialog"):
            await chain.run()
