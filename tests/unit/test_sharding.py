"""Step 5.3 TaskShardingEngine 单元测试。"""

import pytest

from orbit.sharding.engine import (
    MAX_CHARS_PER_TASK,
    MAX_SHARDS,
    ShardStatus,
    TaskShardingEngine,
)


class TestTaskShardingEngine:
    """分片引擎——检测/分片/执行/合并。"""

    @pytest.fixture
    def engine(self) -> TaskShardingEngine:
        return TaskShardingEngine()

    def test_should_shard_small_prd(self, engine: TaskShardingEngine) -> None:
        """短 PRD 不需要分片。"""
        assert engine.should_shard("短需求") is False

    def test_should_shard_large_prd(self, engine: TaskShardingEngine) -> None:
        """长 PRD 需要分片。"""
        assert engine.should_shard("x" * (MAX_CHARS_PER_TASK + 1)) is True

    def test_shard_small_returns_single(self, engine: TaskShardingEngine) -> None:
        """短 PRD——单分片。"""
        plan = engine.shard("短需求", "task-1")
        assert plan.total == 1
        assert plan.shards[0].content == "短需求"

    def test_shard_by_paragraphs(self, engine: TaskShardingEngine) -> None:
        """按段落边界分片。"""
        para = "x" * 3000
        prd = "\n\n".join([para] * 4)  # 12000 chars, 4 paragraphs
        plan = engine.shard(prd, "task-2")
        # 每段 3000 chars，每块最多 8000 → 至少 2 个分片
        assert plan.total >= 2

    def test_shard_preserves_order(self, engine: TaskShardingEngine) -> None:
        """分片按原始顺序编号。"""
        para = "x" * 6000
        prd = "\n\n".join([para, para, para])  # 3 big paragraphs
        plan = engine.shard(prd, "task-3")
        indices = [s.shard_index for s in plan.shards]
        assert indices == sorted(indices)
        # 第一个分片内容应包含第一段
        assert para in plan.shards[0].content

    def test_shard_max_limit(self, engine: TaskShardingEngine) -> None:
        """超过 MAX_SHARDS 时分片截断。"""
        # 生成超过 MAX_SHARDS 数量的段落
        many_paras = "\n\n".join(["paragraph"] * (MAX_SHARDS + 10))
        plan = engine.shard(many_paras, "task-4")
        assert plan.total <= MAX_SHARDS + 1  # 可能多 1 个（最后一块）

    def test_shard_plan_progress(self, engine: TaskShardingEngine) -> None:
        """ShardPlan.progress 计算正确。"""
        para = "x" * 6000
        prd = "\n\n".join([para] * 3)
        plan = engine.shard(prd, "task-5")
        assert plan.progress == 0.0  # 初始为 0
        plan.shards[0].status = ShardStatus.COMPLETED
        assert plan.progress > 0.0

    def test_merge_results_ordered(self, engine: TaskShardingEngine) -> None:
        """合并结果按 shard_index 排序。"""
        para = "x" * 6000
        prd = "\n\n".join([para] * 3)
        plan = engine.shard(prd, "task-6")
        for s in plan.shards:
            s.status = ShardStatus.COMPLETED
            s.output = f"output-{s.shard_index}"
        merged = engine.merge_results(plan)
        # 验证顺序：索引 0 应在索引 1 之前
        assert merged.find("output-0") < merged.find("output-1")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_execute_single_shard(self, engine: TaskShardingEngine) -> None:
        """短 PRD 直接执行（不并发）。"""
        plan = await engine.execute("短需求", "task-exec-1")
        assert plan.total == 1
        assert plan.shards[0].status == ShardStatus.COMPLETED
        assert plan.shards[0].duration_ms > 0

    @pytest.mark.asyncio(loop_scope="function")
    async def test_execute_multi_shard(self, engine: TaskShardingEngine) -> None:
        """多分片并发执行。"""
        para = "x" * 3000
        prd = "\n\n".join([para] * 4)
        plan = await engine.execute(prd, "task-exec-2")
        assert plan.total >= 2
        # 所有分片应完成
        for s in plan.shards:
            assert s.status == ShardStatus.COMPLETED, f"Shard {s.shard_index} failed: {s.error}"

    # ── 覆盖缺口 ──

    def test_shard_plan_failed_property(self) -> None:
        """ShardPlan.failed 计算正确（line 65）。"""
        from orbit.sharding.engine import ShardPlan, ShardResult
        plan = ShardPlan(
            parent_task_id="t",
            shards=[
                ShardResult(shard_id="0", shard_index=0, content="a", status=ShardStatus.FAILED),
                ShardResult(shard_id="1", shard_index=1, content="b", status=ShardStatus.COMPLETED),
            ],
        )
        assert plan.failed == 1

    def test_shard_plan_progress_empty(self) -> None:
        """空分片列表 → progress 返回 0.0（line 70）。"""
        from orbit.sharding.engine import ShardPlan
        plan = ShardPlan(parent_task_id="t", shards=[])
        assert plan.progress == 0.0

    @pytest.mark.asyncio(loop_scope="function")
    async def test_execute_single_shard_exception(self, engine: TaskShardingEngine) -> None:
        """单分片执行异常 → FAILED 状态（lines 172-174）。"""
        from unittest.mock import AsyncMock
        engine._scheduler.run_task = AsyncMock(side_effect=RuntimeError("boom"))
        plan = await engine.execute("短需求", "task-exec-err")
        assert plan.shards[0].status == ShardStatus.FAILED
        assert "boom" in plan.shards[0].error
