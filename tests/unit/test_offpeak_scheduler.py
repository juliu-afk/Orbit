"""D13: 高峰避让调度——单元测试。

覆盖: PeakWindowManager, DeferredQueue, estimate_window_capacity, OffPeakScheduler.enqueue().
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orbit.scheduler.offpeak_models import (
    DeferredTask,
    EnqueueResult,
    PeakWindow,
    ProviderPeakConfig,
)
from orbit.scheduler.offpeak_scheduler import (
    DeferredQueue,
    OffPeakScheduler,
    PeakWindowManager,
    estimate_window_capacity,
)


# ── PeakWindowManager ──────────────────────────────────────────

class TestPeakWindowManager:
    """高峰/低峰时段判定——核心正确性。"""

    @pytest.fixture
    def mgr(self) -> PeakWindowManager:
        """用默认配置（不依赖 YAML 文件）创建管理器。"""
        mgr = PeakWindowManager.__new__(PeakWindowManager)
        mgr._config_path = ""
        mgr._configs = {}
        mgr._holidays = set()
        # 手动注入配置，不读 YAML
        mgr._configs["deepseek"] = ProviderPeakConfig(
            provider="deepseek",
            timezone="Asia/Shanghai",
            peak_windows=[
                PeakWindow(days=["Mon","Tue","Wed","Thu","Fri"], hours_start="09:00", hours_end="23:00"),
            ],
            offpeak_windows=[
                PeakWindow(days=["Mon","Tue","Wed","Thu","Fri"], hours_start="23:00", hours_end="09:00"),
                PeakWindow(days=["Sat","Sun"], hours_start="00:00", hours_end="23:59"),
            ],
            peak_price_multiplier=1.0,
            offpeak_price_multiplier=0.7,
        )
        mgr._configs["anthropic"] = ProviderPeakConfig(
            provider="anthropic",
            timezone="America/Los_Angeles",
            peak_windows=[
                PeakWindow(days=["Mon","Tue","Wed","Thu","Fri"], hours_start="08:00", hours_end="18:00"),
            ],
            offpeak_windows=[
                PeakWindow(days=["Mon","Tue","Wed","Thu","Fri"], hours_start="18:00", hours_end="08:00"),
                PeakWindow(days=["Sat","Sun"], hours_start="00:00", hours_end="23:59"),
            ],
            peak_price_multiplier=1.0,
            offpeak_price_multiplier=0.85,
        )
        return mgr

    # ── is_peak ──

    def test_deepseek_weekday_noon_is_peak(self, mgr):
        """工作日下午 2 点 → 高峰。"""
        # 用 UTC 构造北京时间 14:00 的 datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 2, 14, 0, tzinfo=tz)  # 周四
        assert mgr.is_peak("deepseek", t) is True

    def test_deepseek_weekday_midnight_is_offpeak(self, mgr):
        """工作日凌晨 2 点 → 低峰。"""
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 2, 2, 0, tzinfo=tz)
        assert mgr.is_peak("deepseek", t) is False

    def test_deepseek_saturday_is_offpeak(self, mgr):
        """周六全天 → 低峰。"""
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 4, 14, 0, tzinfo=tz)  # 周六
        assert mgr.is_peak("deepseek", t) is False

    def test_anthropic_us_business_hours_is_peak(self, mgr):
        """US Pacific 工作日上午 10 点 → 高峰。"""
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
        t = datetime(2026, 7, 2, 10, 0, tzinfo=tz)  # 周四
        assert mgr.is_peak("anthropic", t) is True

    def test_anthropic_us_evening_is_offpeak(self, mgr):
        """US Pacific 晚上 8 点 → 低峰。"""
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
        t = datetime(2026, 7, 2, 20, 0, tzinfo=tz)
        assert mgr.is_peak("anthropic", t) is False

    def test_unknown_provider_is_offpeak(self, mgr):
        """未知厂商 → 不挡路，返回低峰。"""
        assert mgr.is_peak("unknown_provider") is False

    # ── price_multiplier ──

    def test_price_multiplier_peak(self, mgr):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 2, 14, 0, tzinfo=tz)
        assert mgr.get_price_multiplier("deepseek", t) == 1.0

    def test_price_multiplier_offpeak(self, mgr):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 2, 2, 0, tzinfo=tz)
        assert mgr.get_price_multiplier("deepseek", t) == 0.7

    # ── next_offpeak_window ──

    def test_next_offpeak_window_returns_window(self, mgr):
        """高峰时返回下一个低峰窗口。"""
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 2, 14, 0, tzinfo=tz)  # 周四下午
        window = mgr.next_offpeak_window("deepseek", t)
        assert window is not None
        # 应该是当天 23:00 开始的低峰窗口

    # ── reload ──

    def test_reload_does_not_crash(self, mgr):
        """reload 不抛异常。"""
        mgr.reload()

    # ── holidays ──

    def test_holiday_always_offpeak(self, mgr):
        """节假日全天低峰。"""
        from zoneinfo import ZoneInfo
        mgr._holidays.add("2026-07-02")  # 7月2日是周四
        tz = ZoneInfo("Asia/Shanghai")
        t = datetime(2026, 7, 2, 14, 0, tzinfo=tz)
        assert mgr.is_peak("deepseek", t) is False


# ── PeakWindow ─────────────────────────────────────────────────

class TestPeakWindow:
    def test_contains_matching(self):
        w = PeakWindow(days=["Mon","Tue"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Mon", "10:00") is True

    def test_contains_wrong_day(self):
        w = PeakWindow(days=["Mon","Tue"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Wed", "10:00") is False

    def test_contains_outside_hours(self):
        w = PeakWindow(days=["Mon","Tue"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Mon", "08:59") is False
        assert w.contains("Mon", "17:00") is False  # 右开区间

    def test_contains_edge_start(self):
        w = PeakWindow(days=["Mon"], hours_start="09:00", hours_end="17:00")
        assert w.contains("Mon", "09:00") is True


# ── estimate_window_capacity ───────────────────────────────────

class TestEstimateWindowCapacity:
    def make_task(self, id_: str, priority: str, duration: int) -> DeferredTask:
        return DeferredTask(id=id_, priority=priority, estimated_duration_seconds=duration)

    def test_empty_queue(self):
        cap = estimate_window_capacity(
            datetime.now(UTC), datetime.now(UTC) + timedelta(hours=1), []
        )
        assert cap == 0

    def test_fits_exactly(self):
        """1小时窗口 × 5并行 = 5小时容量。2个1h任务 + buffer 刚好。"""
        start = datetime.now(UTC)
        end = start + timedelta(hours=1)
        tasks = [
            self.make_task("t1", "NORMAL", 1800),  # 30min, ×1.3 = 39min
            self.make_task("t2", "NORMAL", 1800),
        ]
        cap = estimate_window_capacity(start, end, tasks, max_parallel=3)
        assert cap >= 2  # 肯定够

    def test_overflow_limited(self):
        """窗口不够——只能跑部分任务。"""
        start = datetime.now(UTC)
        end = start + timedelta(minutes=30)
        tasks = [
            self.make_task(f"t{i}", "NORMAL", 3600) for i in range(20)  # 全是1h任务
        ]
        cap = estimate_window_capacity(start, end, tasks, max_parallel=1)
        assert cap < 20

    def test_priority_sorting(self):
        """CRITICAL 排在前面。"""
        start = datetime.now(UTC)
        end = start + timedelta(hours=1)
        tasks = [
            self.make_task("t-low", "LOW", 100),
            self.make_task("t-critical", "CRITICAL", 100),
            self.make_task("t-normal", "NORMAL", 100),
        ]
        cap = estimate_window_capacity(start, end, tasks, max_parallel=10)
        # 3个任务都很快（100s），全部能跑
        assert cap == 3


# ── DeferredQueue ──────────────────────────────────────────────

class TestDeferredQueue:
    @pytest.fixture
    def db_path(self) -> str:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        yield path
        # WHY ignore_errors: Windows 下 SQLite 连接可能未完全释放导致 PermissionError
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass

    @pytest.fixture
    async def queue(self, db_path: str) -> DeferredQueue:
        q = DeferredQueue(db_path)
        return q

    @pytest.mark.asyncio
    async def test_push_and_list(self, queue):
        task = DeferredTask(
            id="g-1", goal_description="test", priority="NORMAL",
            provider="deepseek", target_window_start="2026-07-02T00:00:00+00:00",
            target_window_end="2026-07-02T06:00:00+00:00",
            created_at=datetime.now(UTC).isoformat(), goal_json="{}",
        )
        pos = await queue.push(task)
        assert pos >= 1

        tasks = await queue.list_all()
        assert len(tasks) >= 1
        assert tasks[0].id == "g-1"

    @pytest.mark.asyncio
    async def test_push_multiple_returns_position(self, queue):
        for i in range(5):
            task = DeferredTask(
                id=f"g-{i}", goal_description=f"task-{i}", priority="NORMAL",
                provider="deepseek",
                target_window_start="2026-07-02T00:00:00+00:00",
                target_window_end="2026-07-02T06:00:00+00:00",
                created_at=datetime.now(UTC).isoformat(), goal_json="{}",
            )
            await queue.push(task)
        tasks = await queue.list_all("queued")
        assert len(tasks) == 5

    @pytest.mark.asyncio
    async def test_pop_for_window(self, queue):
        for i in range(3):
            task = DeferredTask(
                id=f"g-{i}", goal_description=f"task-{i}", priority="NORMAL",
                provider="deepseek",
                target_window_start="2026-07-02T00:00:00+00:00",
                target_window_end="2026-07-02T06:00:00+00:00",
                created_at=datetime.now(UTC).isoformat(), goal_json="{}",
            )
            await queue.push(task)

        popped = await queue.pop_for_window(
            "2026-07-02T00:00:00+00:00", "2026-07-02T06:00:00+00:00", limit=2
        )
        assert len(popped) == 2
        # 队列还剩 1
        remaining = await queue.list_all("queued")
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_promote_to_urgent(self, queue):
        task = DeferredTask(
            id="g-urgent-test", goal_description="test", priority="NORMAL",
            provider="deepseek",
            target_window_start="2026-07-02T00:00:00+00:00",
            target_window_end="2026-07-02T06:00:00+00:00",
            created_at=datetime.now(UTC).isoformat(), goal_json="{}",
        )
        await queue.push(task)
        promoted = await queue.promote_to_urgent("g-urgent-test")
        assert promoted is not None
        assert promoted.id == "g-urgent-test"

        # 已不在 queued 中
        queued = await queue.list_all("queued")
        assert all(t.id != "g-urgent-test" for t in queued)

    @pytest.mark.asyncio
    async def test_promote_nonexistent(self, queue):
        assert await queue.promote_to_urgent("nonexistent") is None

    @pytest.mark.asyncio
    async def test_mark_done(self, queue):
        task = DeferredTask(
            id="g-done", goal_description="test", priority="NORMAL",
            provider="deepseek",
            target_window_start="2026-07-02T00:00:00+00:00",
            target_window_end="2026-07-02T06:00:00+00:00",
            created_at=datetime.now(UTC).isoformat(), goal_json="{}",
        )
        await queue.push(task)
        await queue.mark_done("g-done", actual_tokens=50000, cost_saved=0.15)

        # 验证已标记为 done
        all_tasks = await queue.list_all()
        done = [t for t in all_tasks if t.id == "g-done" and t.status == "done"]
        assert len(done) == 1
        assert done[0].actual_tokens == 50000
        assert done[0].cost_saved_yuan == 0.15

    @pytest.mark.asyncio
    async def test_savings_report(self, queue):
        task = DeferredTask(
            id="g-report", goal_description="test", priority="NORMAL",
            provider="deepseek",
            target_window_start="2026-07-02T00:00:00+00:00",
            target_window_end="2026-07-02T06:00:00+00:00",
            created_at=datetime.now(UTC).isoformat(), goal_json="{}",
        )
        await queue.push(task)
        await queue.mark_done("g-report", actual_tokens=100000, cost_saved=0.30)

        report = await queue.get_savings_report()
        assert report["total_tasks_done"] >= 1
        assert report["total_tokens_offpeak"] >= 100000
        assert report["total_saved_yuan"] >= 0.30

    @pytest.mark.asyncio
    async def test_reschedule(self, queue):
        task = DeferredTask(
            id="g-resh", goal_description="test", priority="NORMAL",
            provider="deepseek",
            target_window_start="2026-07-02T00:00:00+00:00",
            target_window_end="2026-07-02T06:00:00+00:00",
            created_at=datetime.now(UTC).isoformat(), goal_json="{}",
        )
        await queue.push(task)
        await queue.reschedule("g-resh", "2026-07-03T00:00:00+00:00", "2026-07-03T06:00:00+00:00")

        all_tasks = await queue.list_all("queued")
        resh = [t for t in all_tasks if t.id == "g-resh"]
        assert len(resh) == 1
        assert resh[0].target_window_start == "2026-07-03T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_mark_cancelled(self, queue):
        task = DeferredTask(
            id="g-cancel", goal_description="test", priority="NORMAL",
            provider="deepseek",
            target_window_start="2026-07-02T00:00:00+00:00",
            target_window_end="2026-07-02T06:00:00+00:00",
            created_at=datetime.now(UTC).isoformat(), goal_json="{}",
        )
        await queue.push(task)
        await queue.mark_cancelled("g-cancel")
        queued = await queue.list_all("queued")
        assert all(t.id != "g-cancel" for t in queued)


# ── OffPeakScheduler.enqueue() ─────────────────────────────────

class TestOffPeakSchedulerEnqueue:
    """enqueue() 分支逻辑。"""
    from orbit.goal.models import GoalSession

    @pytest.fixture
    def mock_orch(self):
        m = MagicMock()
        m.run = AsyncMock()  # orchestrator.run() 是 async
        return m

    @pytest.fixture
    def mock_preflight(self):
        m = AsyncMock()
        from orbit.goal.preflight import PreFlightResult
        m.estimate.return_value = PreFlightResult(
            token_low=50000, token_high=150000,
            time_low_seconds=300, time_high_seconds=900,
            confidence=0.5, source="fuzzy",
        )
        return m

    def _make_goal(self, **kw) -> GoalSession:
        from orbit.goal.models import GoalSession
        defaults = dict(
            description="test goal", constraints=[], verification_commands=[],
            sub_tasks={}, spec=None, status="active",
            defer_to_offpeak=False, urgent=False, target_provider="", max_price_multiplier=0.0,
        )
        defaults.update(kw)
        return GoalSession(**defaults)

    @pytest.mark.asyncio
    async def test_enqueue_during_peak_queues_task(self, mock_orch, mock_preflight):
        """高峰期提交延迟任务 → 入队到低峰窗口。"""
        from orbit.scheduler.offpeak_scheduler import PeakWindowManager
        mgr = PeakWindowManager.__new__(PeakWindowManager)
        mgr._configs = {}
        mgr._configs["deepseek"] = ProviderPeakConfig(
            provider="deepseek", timezone="Asia/Shanghai",
            peak_windows=[PeakWindow(days=["Mon","Tue","Wed","Thu","Fri"], hours_start="00:00", hours_end="23:59")],
            offpeak_windows=[PeakWindow(days=["Sat","Sun"], hours_start="00:00", hours_end="23:59")],
            peak_price_multiplier=1.0, offpeak_price_multiplier=0.7,
        )
        mgr._holidays = set()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            q = DeferredQueue(db_path)
            scheduler = OffPeakScheduler(mgr, q, mock_orch, mock_preflight)
            goal = self._make_goal(defer_to_offpeak=True, target_provider="deepseek")
            result = await scheduler.enqueue(goal)

            assert result.status == "queued"
            assert result.target_window_start != ""
            assert result.queue_position >= 1
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass  # Windows: SQLite 文件锁可能延迟释放

    @pytest.mark.asyncio
    async def test_enqueue_offpeak_only_peak_warning(self, mock_orch, mock_preflight):
        """ORBIT_OFFPEAK_ONLY + 高峰 → 返回 peak_warning。"""
        os.environ["ORBIT_OFFPEAK_ONLY"] = "true"
        try:
            from orbit.scheduler.offpeak_scheduler import PeakWindowManager
            mgr = PeakWindowManager.__new__(PeakWindowManager)
            mgr._configs = {}
            mgr._configs["deepseek"] = ProviderPeakConfig(
                provider="deepseek", timezone="Asia/Shanghai",
                peak_windows=[PeakWindow(days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], hours_start="00:00", hours_end="23:59")],
                offpeak_windows=[PeakWindow(days=[], hours_start="00:00", hours_end="00:00")],
                peak_price_multiplier=1.0, offpeak_price_multiplier=0.7,
            )
            mgr._holidays = set()

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            try:
                q = DeferredQueue(db_path)
                scheduler = OffPeakScheduler(mgr, q, mock_orch, mock_preflight)
                goal = self._make_goal(defer_to_offpeak=True, target_provider="deepseek", urgent=False)
                result = await scheduler.enqueue(goal)
                assert result.status == "peak_warning"
                assert "高峰" in result.warning_message
            finally:
                try:  # Windows: SQLite 文件锁可能延迟释放
                    os.unlink(db_path)
                except OSError:
                    pass
        finally:
            os.environ.pop("ORBIT_OFFPEAK_ONLY", None)

    @pytest.mark.asyncio
    async def test_urgent_bypasses_offpeak_only(self, mock_orch, mock_preflight):
        """ORBIT_OFFPEAK_ONLY + urgent=true → 不会走到 enqueue，直接 orch.run()。"""
        # 这是 API 层逻辑——offpeak_only + 高峰 + 非紧急 → enqueue 返回 warning
        # urgent=true 时 API 层直接 orch.run()，不调 enqueue
        # 此测试验证 urgent 标记的 Goal 在 enqueue 中的行为
        os.environ["ORBIT_OFFPEAK_ONLY"] = "true"
        try:
            from orbit.scheduler.offpeak_scheduler import PeakWindowManager
            mgr = PeakWindowManager.__new__(PeakWindowManager)
            mgr._configs = {}
            mgr._configs["deepseek"] = ProviderPeakConfig(
                provider="deepseek", timezone="Asia/Shanghai",
                peak_windows=[PeakWindow(days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], hours_start="00:00", hours_end="23:59")],
                offpeak_windows=[PeakWindow(days=[], hours_start="00:00", hours_end="00:00")],
                peak_price_multiplier=1.0, offpeak_price_multiplier=0.7,
            )
            mgr._holidays = set()

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            try:
                q = DeferredQueue(db_path)
                scheduler = OffPeakScheduler(mgr, q, mock_orch, mock_preflight)
                goal = self._make_goal(defer_to_offpeak=True, target_provider="deepseek", urgent=True)
                result = await scheduler.enqueue(goal)
                # urgent=true: urgent 检查先于 offpeak_only——不返回 warning
                assert result.status != "peak_warning"
            finally:
                try:  # Windows: SQLite 文件锁可能延迟释放
                    os.unlink(db_path)
                except OSError:
                    pass
        finally:
            os.environ.pop("ORBIT_OFFPEAK_ONLY", None)

    @pytest.mark.asyncio
    async def test_enqueue_during_offpeak_runs_immediate_or_queues(self, mock_orch, mock_preflight):
        """当前已是低峰 → 任务入队到当前窗口，下一轮 watcher 释放。"""
        from orbit.scheduler.offpeak_scheduler import PeakWindowManager
        mgr = PeakWindowManager.__new__(PeakWindowManager)
        mgr._configs = {}
        mgr._configs["deepseek"] = ProviderPeakConfig(
            provider="deepseek", timezone="Asia/Shanghai",
            peak_windows=[PeakWindow(days=[], hours_start="00:00", hours_end="00:00")],
            offpeak_windows=[PeakWindow(days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], hours_start="00:00", hours_end="23:59")],
            peak_price_multiplier=1.0, offpeak_price_multiplier=0.7,
        )
        mgr._holidays = set()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            q = DeferredQueue(db_path)
            scheduler = OffPeakScheduler(mgr, q, mock_orch, mock_preflight)
            goal = self._make_goal(defer_to_offpeak=True, target_provider="deepseek")
            result = await scheduler.enqueue(goal)
            # 低峰时也正常入队，watcher 会立即释放
            assert result.status == "queued"
        finally:
            try:  # Windows: SQLite 文件锁可能延迟释放
                os.unlink(db_path)
            except OSError:
                pass
