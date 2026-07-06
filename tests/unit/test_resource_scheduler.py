"""Step 5.6 PR #3——资源调度器单元测试。"""

from orbit.scheduler.resource_scheduler import (
    ResourceQuota,
    ResourceScheduler,
    TaskPriority,
)


class TestResourceScheduler:
    """资源调度——提交/排队/抢占/配额/降级。"""

    def test_submit_within_capacity(self) -> None:
        sched = ResourceScheduler(ResourceQuota(max_concurrent_tasks=3))
        assert sched.submit("t1", TaskPriority.NORMAL) is True
        assert sched.submit("t2", TaskPriority.NORMAL) is True
        assert sched.get_queue_status()["active"] == 2

    def test_submit_over_capacity_queues(self) -> None:
        """超出并发上限 → 排队。"""
        sched = ResourceScheduler(ResourceQuota(max_concurrent_tasks=2))
        sched.submit("t1", TaskPriority.NORMAL)
        sched.submit("t2", TaskPriority.NORMAL)
        # 第 3 个排队
        assert sched.submit("t3", TaskPriority.NORMAL) is False
        assert sched.get_queue_status()["normal"] == 1

    def test_critical_preempts_low(self) -> None:
        """CRITICAL 可抢占 LOW。"""
        sched = ResourceScheduler(ResourceQuota(max_concurrent_tasks=1))
        sched.submit("t-low", TaskPriority.LOW)
        # CRITICAL 抢占
        assert sched.submit("t-critical", TaskPriority.CRITICAL) is True
        assert sched.get_task("t-low") is None  # 被抢占

    def test_can_proceed_token_budget(self) -> None:
        sched = ResourceScheduler(ResourceQuota(max_tokens_per_task=100))
        sched.submit("t1", TaskPriority.NORMAL)
        sched.consume_llm_call("t1", tokens=80)
        # 再消耗 30 → 超限
        assert sched.can_proceed("t1", estimated_tokens=30) is False

    def test_llm_rate_limit(self) -> None:
        """全局 LLM 调用限流——超限返回 False。"""
        sched = ResourceScheduler(ResourceQuota(max_llm_calls_per_minute=2))
        sched.submit("t1")
        assert sched.consume_llm_call("t1", tokens=10) is True
        assert sched.consume_llm_call("t1", tokens=10) is True
        assert sched.consume_llm_call("t1", tokens=10) is False  # 超限

    def test_release_frees_slot(self) -> None:
        sched = ResourceScheduler(ResourceQuota(max_concurrent_tasks=2))
        sched.submit("t1")
        sched.submit("t2")
        assert sched.get_queue_status()["active"] == 2
        sched.release("t1")
        assert sched.get_queue_status()["active"] == 1

    def test_queue_status(self) -> None:
        sched = ResourceScheduler(ResourceQuota(max_concurrent_tasks=1))
        sched.submit("t1", TaskPriority.CRITICAL)
        sched.submit("t2", TaskPriority.LOW)  # 排队
        sched.submit("t3", TaskPriority.LOW)  # 排队
        status = sched.get_queue_status()
        assert status["critical"] == 0
        assert status["low"] == 2
        assert status["active"] == 1

    def test_unknown_task_can_proceed(self) -> None:
        sched = ResourceScheduler()
        assert sched.can_proceed("nonexistent") is False

    # -- 覆盖缺口 --

    def test_critical_preempts_active_low(self) -> None:
        """CRITICAL 抢占已在运行中的 LOW 任务（lines 132-150）。"""
        sched = ResourceScheduler(ResourceQuota(max_concurrent_tasks=1))
        sched.submit("t-low", TaskPriority.LOW)
        # t-low 已活跃，再用 CRITICAL 抢占
        assert sched.submit("t-critical", TaskPriority.CRITICAL) is True
        assert sched.get_task("t-low") is None  # 被抢占
        assert sched.get_task("t-critical") is not None

    def test_sandbox_limit_can_proceed(self) -> None:
        """沙箱实例超限 → can_proceed=False（line 174-175）。"""
        sched = ResourceScheduler(ResourceQuota(max_sandbox_instances=0))
        sched.submit("t1")
        assert sched.can_proceed("t1") is False

    def test_long_run_demotion(self) -> None:
        """长时间运行任务 → 降级 LOW（lines 178-180）。"""
        sched = ResourceScheduler(
            ResourceQuota(long_run_threshold_seconds=-1)  # 立即触发
        )
        sched.submit("t1", TaskPriority.HIGH)
        sched.can_proceed("t1")  # 触发降级
        t = sched.get_task("t1")
        assert t is not None
        assert t.priority == TaskPriority.LOW
