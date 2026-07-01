"""高峰避让调度器——OffPeakScheduler + PeakWindowManager + DeferredQueue。

WHY 三合一文件: 三者紧密耦合——PeakWindowManager 判定时间，
DeferredQueue 持久化队列，OffPeakScheduler 协调两者 + MetaOrchestrator。
拆开会导致循环引用。

Usage:
    peak_mgr = PeakWindowManager("configs/peak_windows.yaml")
    queue = DeferredQueue("data/offpeak.db")
    offpeak = OffPeakScheduler(peak_mgr, queue, orchestrator, preflight)
    await offpeak.start()  # 启动后台 window_watcher
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import structlog
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml

from orbit.scheduler.offpeak_models import (
    DeferredStatus,
    DeferredTask,
    EnqueueResult,
    PeakStatus,
    PeakWindow,
    ProviderPeakConfig,
)

if TYPE_CHECKING:
    from orbit.goal.models import GoalSession
    from orbit.goal.meta_orchestrator import MetaOrchestrator
    from orbit.goal.preflight import PreFlightEstimator

logger = structlog.get_logger("orbit.offpeak")

# 默认高峰配置——YAML 加载失败时的兜底
DEFAULT_PEAK_CONFIGS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "timezone": "Asia/Shanghai",
        "peak_windows": [{"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "09:00-23:00"}],
        "offpeak_windows": [
            {"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "23:00-09:00"},
            {"days": ["Sat","Sun"], "hours": "00:00-24:00"},
        ],
        "peak_price_multiplier": 1.0,
        "offpeak_price_multiplier": 0.7,
    },
    "anthropic": {
        "timezone": "America/Los_Angeles",
        "peak_windows": [{"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "08:00-18:00"}],
        "offpeak_windows": [
            {"days": ["Mon","Tue","Wed","Thu","Fri"], "hours": "18:00-08:00"},
            {"days": ["Sat","Sun"], "hours": "00:00-24:00"},
        ],
        "peak_price_multiplier": 1.0,
        "offpeak_price_multiplier": 0.85,
    },
}


# ── PeakWindowManager ──────────────────────────────────────────

class PeakWindowManager:
    """高峰/低峰时段管理器。

    WHY YAML + env override: YAML 方便运维手动编辑，
    env 方便 CI/容器覆盖。启动时加载，运行时通过 reload() 热更新。
    """

    def __init__(self, config_path: str = "configs/peak_windows.yaml") -> None:
        self._config_path = config_path
        self._configs: dict[str, ProviderPeakConfig] = {}
        self._holidays: set[str] = set()  # "2026-07-04", ...
        self._load_config()
        self._load_holidays()

    # ── 公共 API ──

    @property
    def providers(self) -> list[str]:
        return list(self._configs.keys())

    def is_peak(self, provider: str, at: datetime | None = None) -> bool:
        """判定指定厂商在当前时间是否处于高峰。

        Args:
            provider: 厂商名（deepseek/anthropic/openai/glm）
            at: 可选——判定时间点，默认 now()

        Returns:
            True = 高峰期，False = 低峰期
        """
        config = self._configs.get(provider)
        if config is None:
            return False  # 未知厂商——不阻挡

        now = at or datetime.now(UTC)
        try:
            from zoneinfo import ZoneInfo
            local = now.astimezone(ZoneInfo(config.timezone))
        except Exception:
            # 时区不可用 → 保守判定为低峰
            return False

        day_name = local.strftime("%a")  # Mon, Tue, ...
        date_str = local.strftime("%Y-%m-%d")

        # 节假日 → 全天低峰
        if date_str in self._holidays:
            return False

        time_str = local.strftime("%H:%M")
        return any(w.contains(day_name, time_str) for w in config.peak_windows)

    def next_offpeak_window(
        self, provider: str, after: datetime | None = None
    ) -> PeakWindow | None:
        """返回下一个低峰窗口。

        WHY 向前搜索最多 7 天: 避免无限循环——周末一定在 7 天内。
        """
        config = self._configs.get(provider)
        if config is None:
            return None

        from zoneinfo import ZoneInfo

        tz = ZoneInfo(config.timezone)
        now = after or datetime.now(UTC)
        local_now = now.astimezone(tz)

        # 向前搜索最多 7 天
        for offset_days in range(8):
            check_date = local_now.date() + timedelta(days=offset_days)
            day_name = check_date.strftime("%a")

            for window in config.offpeak_windows:
                if day_name not in window.days:
                    continue

                # 构造窗口的开始时间
                start_h, start_m = map(int, window.hours_start.split(":"))
                end_h, end_m = map(int, window.hours_end.split(":"))

                window_start = datetime(
                    check_date.year, check_date.month, check_date.day,
                    start_h, start_m, tzinfo=tz,
                )
                window_end = datetime(
                    check_date.year, check_date.month, check_date.day,
                    end_h, end_m, tzinfo=tz,
                )

                # 跨天窗口（如 23:00-09:00）——结束时间加一天
                if window_end <= window_start:
                    window_end += timedelta(days=1)

                # 赋值具体 ISO 时间到返回的 PeakWindow
                window.starts_at_iso = window_start.astimezone(UTC).isoformat()
                window.ends_at_iso = window_end.astimezone(UTC).isoformat()

                if after is None and window_start <= now <= window_end:
                    return window

                if window_start > (after or now):
                    return window

        return None  # 7 天内无窗口（不可能——周末全天低峰）

    def get_all_status(self, at: datetime | None = None) -> dict[str, PeakStatus]:
        """返回所有厂商当前高峰状态——供 API 使用。"""
        result: dict[str, PeakStatus] = {}
        now = at or datetime.now(UTC)
        for provider in self._configs:
            peak = self.is_peak(provider, now)
            next_offpeak = self.next_offpeak_window(provider, now)

            status = PeakStatus(
                provider=provider,
                is_peak=peak,
            )
            if peak:
                # 高峰何时结束 → 找到第一个低峰窗口的开始时间
                next_win = self.next_offpeak_window(provider, now)
                if next_win:
                    # 找当前高峰窗口的结束时间
                    config = self._configs[provider]
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(config.timezone)
                    local = now.astimezone(tz)
                    for pw in config.peak_windows:
                        if pw.contains(local.strftime("%a"), local.strftime("%H:%M")):
                            end_h, end_m = map(int, pw.hours_end.split(":"))
                            peak_end = datetime(
                                local.year, local.month, local.day,
                                end_h, end_m, tzinfo=tz,
                            )
                            if peak_end <= datetime(local.year, local.month, local.day, tzinfo=tz):
                                peak_end += timedelta(days=1)
                            status.peak_ends_at = peak_end.astimezone(UTC).isoformat()
                            break

            if next_offpeak:
                status.next_offpeak_starts_at = next_offpeak.starts_at_iso
                status.next_offpeak_ends_at = next_offpeak.ends_at_iso

            result[provider] = status
        return result

    def get_price_multiplier(self, provider: str, at: datetime | None = None) -> float:
        """返回指定厂商在当前时段的价格倍数。"""
        config = self._configs.get(provider)
        if config is None:
            return 1.0
        if self.is_peak(provider, at):
            return config.peak_price_multiplier
        return config.offpeak_price_multiplier

    def reload(self) -> None:
        """重新加载配置文件 + 节假日数据。"""
        self._load_config()
        self._load_holidays()

    # ── 内部 ──

    def _load_config(self) -> None:
        """加载 YAML 配置文件。

        WHY fail-soft: YAML 格式错误不阻止系统启动——用默认配置兜底。
        """
        try:
            path = Path(self._config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                self._parse_config(raw)
                logger.info("peak_config_loaded", path=str(path), providers=list(self._configs.keys()))
            else:
                logger.warning("peak_config_missing", path=str(path), fallback="default_configs")
                self._load_defaults()
        except Exception:
            logger.exception("peak_config_parse_error", path=self._config_path)
            self._load_defaults()

    def _parse_config(self, raw: dict) -> None:
        """解析 YAML → ProviderPeakConfig。"""
        self._configs.clear()
        providers_raw = raw.get("providers", {})
        for name, cfg in providers_raw.items():
            peak_windows = [
                PeakWindow(days=w.get("days", ["Mon","Tue","Wed","Thu","Fri"]), hours_start=w["hours"].split("-")[0], hours_end=w["hours"].split("-")[1])
                for w in cfg.get("peak_windows", [])
            ]
            offpeak_windows_raw = cfg.get("offpeak_windows", [])
            if not offpeak_windows_raw:
                # 从 peak_windows 推导——高峰之外就是低峰
                offpeak_windows_raw = cfg.get("peak_windows", [])
            offpeak_windows = [
                PeakWindow(days=w.get("days", ["Mon","Tue","Wed","Thu","Fri"]), hours_start=w["hours"].split("-")[0], hours_end=w["hours"].split("-")[1])
                for w in offpeak_windows_raw
            ]
            self._configs[name] = ProviderPeakConfig(
                provider=name,
                timezone=cfg.get("timezone", "UTC"),
                peak_windows=peak_windows,
                offpeak_windows=offpeak_windows,
                peak_price_multiplier=cfg.get("peak_price_multiplier", 1.0),
                offpeak_price_multiplier=cfg.get("offpeak_price_multiplier", 1.0),
            )

    def _load_defaults(self) -> None:
        """加载硬编码默认配置——YAML 加载失败时的兜底。"""
        self._parse_config({"providers": DEFAULT_PEAK_CONFIGS})

    def _load_holidays(self) -> None:
        """从 ORBIT_HOLIDAYS_URL 加载节假日列表。

        WHY 异步 HTTP 但不阻塞: 启动时同步加载——URL 通常是本地文件或快速 API。
        若为远程 URL 且超时，降级跳过节假日判定。
        """
        url = os.getenv("ORBIT_HOLIDAYS_URL", "")
        if not url:
            return

        try:
            import urllib.request

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            # 格式: {"2026-07-04": "US Independence Day", ...}
            self._holidays = set(data.keys())
            logger.info("holidays_loaded", count=len(self._holidays), url=url)
        except Exception:
            logger.warning("holidays_load_failed", url=url)


# ── DeferredQueue ──────────────────────────────────────────────

class DeferredQueue:
    """延迟执行队列——SQLite 持久化。

    WHY raw sqlite3: 遵循 LoopScheduler/SessionRegistry 的已有模式。
    没有 async ORM 的历史包袱。所有写操作由 asyncio.Lock 保护。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    # ── 公共 API ──

    async def push(self, task: DeferredTask) -> int:
        """入队——返回队列位置（同窗口内排第几）。"""
        async with self._lock:
            return await asyncio.to_thread(self._push_sync, task)

    async def pop_for_window(
        self, window_start: str, window_end: str, limit: int
    ) -> list[DeferredTask]:
        """取出指定窗口内的排队任务——按优先级+预估耗时排序。

        取出的任务 status 由 queued → released 前端不直接调 orch.run()，
        调用方负责 mark_released→执行→mark_done。
        """
        async with self._lock:
            return await asyncio.to_thread(
                self._pop_for_window_sync, window_start, window_end, limit
            )

    async def list_all(self, status_filter: str | None = None) -> list[DeferredTask]:
        """列出排队任务——供 API 和 watcher 使用。"""
        async with self._lock:
            return await asyncio.to_thread(self._list_all_sync, status_filter)

    async def promote_to_urgent(self, goal_id: str) -> DeferredTask | None:
        """将排队任务提升为立即执行——返回 task 供调用方直接 orch.run()。

        状态: queued → urgent_override
        """
        async with self._lock:
            return await asyncio.to_thread(self._promote_sync, goal_id)

    async def mark_released(self, goal_id: str) -> None:
        """标记任务已释放到执行器。queued → released。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_released_sync, goal_id)

    async def mark_done(
        self, goal_id: str, actual_tokens: int, cost_saved: float
    ) -> None:
        """标记任务完成 + 记录实际消耗和节省金额。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_done_sync, goal_id, actual_tokens, cost_saved)

    async def mark_cancelled(self, goal_id: str) -> None:
        """取消排队中的任务。"""
        async with self._lock:
            await asyncio.to_thread(self._mark_cancelled_sync, goal_id)

    async def get_savings_report(self) -> dict:
        """查询成本节省统计——供 savings-report API。"""
        async with self._lock:
            return await asyncio.to_thread(self._savings_report_sync)

    async def reschedule(
        self, goal_id: str, new_window_start: str, new_window_end: str
    ) -> None:
        """将任务重新调度到另一个窗口——窗口溢出时用。"""
        async with self._lock:
            await asyncio.to_thread(
                self._reschedule_sync, goal_id, new_window_start, new_window_end
            )

    # ── 同步内部实现 ──

    def _connect(self) -> sqlite3.Connection:
        """每次操作创建新连接——线程安全，遵循 LoopScheduler 模式。"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deferred_tasks (
                    id TEXT PRIMARY KEY,
                    goal_description TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'NORMAL',
                    provider TEXT NOT NULL DEFAULT '',
                    estimated_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_duration_seconds INTEGER NOT NULL DEFAULT 0,
                    target_window_start TEXT NOT NULL DEFAULT '',
                    target_window_end TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TEXT NOT NULL,
                    released_at TEXT,
                    completed_at TEXT,
                    actual_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_saved_yuan REAL NOT NULL DEFAULT 0.0,
                    goal_json TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_status ON deferred_tasks(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_window ON deferred_tasks(target_window_start, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_provider ON deferred_tasks(provider, status)"
            )
            conn.commit()

    def _push_sync(self, task: DeferredTask) -> int:
        now_iso = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO deferred_tasks
                   (id, goal_description, priority, provider, estimated_tokens,
                    estimated_duration_seconds, target_window_start, target_window_end,
                    status, created_at, goal_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)""",
                (
                    task.id, task.goal_description, task.priority, task.provider,
                    task.estimated_tokens, task.estimated_duration_seconds,
                    task.target_window_start, task.target_window_end,
                    now_iso, task.goal_json,
                ),
            )
            conn.commit()

            # 计算同窗口内的位置——同一连接内查询，保证一致性
            count_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM deferred_tasks WHERE status='queued'"
                " AND target_window_start = ?",
                (task.target_window_start,),
            ).fetchone()
            return count_row["cnt"] if count_row else 0

    def _pop_for_window_sync(
        self, window_start: str, window_end: str, limit: int
    ) -> list[DeferredTask]:
        with self._connect() as conn:
            # 按优先级排序: CRITICAL < HIGH < NORMAL < LOW，同优先级按预估耗时升序
            rows = conn.execute(
                """SELECT * FROM deferred_tasks
                   WHERE status = 'queued'
                     AND target_window_start = ?
                   ORDER BY
                     CASE priority
                       WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                       WHEN 'NORMAL' THEN 2 WHEN 'LOW' THEN 3
                       ELSE 3 END,
                     estimated_duration_seconds ASC
                   LIMIT ?""",
                (window_start, limit),
            ).fetchall()

            tasks = []
            for row in rows:
                # 先标记为 released
                conn.execute(
                    "UPDATE deferred_tasks SET status='released', released_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), row["id"]),
                )
                tasks.append(self._row_to_task(row))
            conn.commit()
            return tasks

    def _list_all_sync(self, status_filter: str | None = None) -> list[DeferredTask]:
        with self._connect() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM deferred_tasks WHERE status = ? ORDER BY created_at ASC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM deferred_tasks ORDER BY created_at ASC"
                ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def _promote_sync(self, goal_id: str) -> DeferredTask | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM deferred_tasks WHERE id = ? AND status = 'queued'",
                (goal_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE deferred_tasks SET status='urgent_override', released_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), goal_id),
            )
            conn.commit()
            return self._row_to_task(row)

    def _mark_released_sync(self, goal_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE deferred_tasks SET status='released', released_at=? WHERE id=? AND status='queued'",
                (datetime.now(UTC).isoformat(), goal_id),
            )
            conn.commit()

    def _mark_done_sync(
        self, goal_id: str, actual_tokens: int, cost_saved: float
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE deferred_tasks
                   SET status='done', completed_at=?, actual_tokens=?, cost_saved_yuan=?
                   WHERE id=?""",
                (datetime.now(UTC).isoformat(), actual_tokens, cost_saved, goal_id),
            )
            conn.commit()

    def _mark_cancelled_sync(self, goal_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE deferred_tasks SET status='cancelled' WHERE id=? AND status='queued'",
                (goal_id,),
            )
            conn.commit()

    def _savings_report_sync(self) -> dict:
        with self._connect() as conn:
            # 已完成任务统计
            total_row = conn.execute(
                """SELECT COUNT(*) as cnt, SUM(actual_tokens) as tokens,
                          SUM(cost_saved_yuan) as saved
                   FROM deferred_tasks WHERE status = 'done'"""
            ).fetchone()

            # 按厂商分拆
            by_provider_rows = conn.execute(
                """SELECT provider, COUNT(*) as cnt, SUM(actual_tokens) as tokens,
                          SUM(cost_saved_yuan) as saved
                   FROM deferred_tasks WHERE status = 'done'
                   GROUP BY provider"""
            ).fetchall()

            # 队列中的
            queued_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM deferred_tasks WHERE status = 'queued'"
            ).fetchone()

            return {
                "total_tasks_deferred": (total_row["cnt"] or 0) + (queued_count["cnt"] or 0),
                "total_tasks_done": total_row["cnt"] or 0,
                "total_tasks_queued": queued_count["cnt"] or 0,
                "total_tokens_offpeak": total_row["tokens"] or 0,
                "total_saved_yuan": round(total_row["saved"] or 0.0, 2),
                "by_provider": [
                    {
                        "provider": r["provider"],
                        "tasks": r["cnt"],
                        "tokens": r["tokens"] or 0,
                        "saved_yuan": round(r["saved"] or 0.0, 2),
                    }
                    for r in by_provider_rows
                ],
            }

    def _reschedule_sync(
        self, goal_id: str, new_window_start: str, new_window_end: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE deferred_tasks
                   SET target_window_start=?, target_window_end=?
                   WHERE id=? AND status='queued'""",
                (new_window_start, new_window_end, goal_id),
            )
            conn.commit()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> DeferredTask:
        return DeferredTask(
            id=row["id"],
            goal_description=row["goal_description"],
            priority=row["priority"],
            provider=row["provider"],
            estimated_tokens=row["estimated_tokens"],
            estimated_duration_seconds=row["estimated_duration_seconds"],
            target_window_start=row["target_window_start"],
            target_window_end=row["target_window_end"],
            status=row["status"],  # type: ignore[arg-type]
            created_at=row["created_at"],
            released_at=row["released_at"],
            completed_at=row["completed_at"],
            actual_tokens=row["actual_tokens"],
            cost_saved_yuan=row["cost_saved_yuan"],
            goal_json=row["goal_json"],
        )


# ── OffPeakScheduler ───────────────────────────────────────────

def estimate_window_capacity(
    window_start: datetime,
    window_end: datetime,
    queued_tasks: list[DeferredTask],
    max_parallel: int = 5,
) -> int:
    """估算低峰窗口能跑几个任务。

    WHY 悲观估算: 用预估耗时的 1.3x 做 buffer。
    WHY 短任务优先: 最大化吞吐——先跑小任务填满窗口。
    """
    window_seconds = (window_end - window_start).total_seconds()
    sorted_tasks = sorted(
        queued_tasks,
        key=lambda t: (
            0 if t.priority in ("CRITICAL", "HIGH") else 1,
            t.estimated_duration_seconds,
        ),
    )
    remaining = window_seconds * max_parallel
    count = 0
    for task in sorted_tasks:
        cost = task.estimated_duration_seconds * 1.3
        if remaining >= cost:
            remaining -= cost
            count += 1
        else:
            break
    return count


class OffPeakScheduler:
    """高峰避让调度器——协调 PeakWindowManager + DeferredQueue + MetaOrchestrator。

    Usage:
        offpeak = OffPeakScheduler(peak_mgr, queue, orchestrator, preflight)
        await offpeak.start()  # 启动后台 window_watcher
        result = await offpeak.enqueue(goal)  # 排队 Goal
    """

    def __init__(
        self,
        peak_manager: PeakWindowManager,
        queue: DeferredQueue,
        orchestrator: MetaOrchestrator,
        preflight: PreFlightEstimator,
    ) -> None:
        self._peak = peak_manager
        self._queue = queue
        self._orch = orchestrator
        self._preflight = preflight
        self._watcher_task: asyncio.Task | None = None
        self._force_offpeak_only = os.getenv("ORBIT_OFFPEAK_ONLY", "") == "true"
        self._watcher_interval = int(os.getenv("ORBIT_OFFPEAK_WATCHER_INTERVAL", "60"))

    # ── 公共属性（供 schedule.py API 路由使用） ──

    @property
    def peak_manager(self):
        return self._peak

    @property
    def queue(self):
        return self._queue

    @property
    def orchestrator(self):
        return self._orch

    # ── 公共 API ──

    async def enqueue(self, goal: GoalSession) -> EnqueueResult:
        """将 Goal 排队到低峰窗口。

        流程:
        1. 调 PreFlightEstimator 预估 token/时间
        2. 判定当前是否高峰 → 确定目标窗口
        3. 构造 DeferredTask → push 到队列

        ORBIT_OFFPEAK_ONLY + 高峰 + 非紧急:
        返回 peak_warning 警告——提示用户确认紧急或等待低峰。
        """
        now = datetime.now(UTC)
        provider = getattr(goal, "target_provider", "") or "deepseek"

        # ── ORBIT_OFFPEAK_ONLY 高峰警告 ──
        if self._force_offpeak_only and self._peak.is_peak(provider, now):
            urgent_flag = getattr(goal, "urgent", False)
            if not urgent_flag:
                next_window = self._peak.next_offpeak_window(provider, now)
                next_start = ""
                if next_window:
                    next_start = next_window.starts_at_iso
                return EnqueueResult(
                    goal_id=goal.id,
                    status="peak_warning",
                    warning_message=(
                        f"当前为 {provider} 高峰期。"
                        f"若需立即执行，请设 urgent=true 后重新提交。"
                        f"下一个低峰窗口: {next_start}"
                    ),
                )

        # ── 预估 ──
        estimate = await self._preflight.estimate(goal.description)
        avg_tokens = (estimate.token_low + estimate.token_high) // 2
        avg_duration = (estimate.time_low_seconds + estimate.time_high_seconds) // 2

        # ── 确定目标窗口 ──
        window = self._peak.next_offpeak_window(provider, now)
        if window is None:
            # 极端情况: 无低峰窗口定义 → 立即执行
            logger.warning("no_offpeak_window_found", provider=provider, goal_id=goal.id)
            task = asyncio.create_task(self._orch.run(goal))
            return EnqueueResult(
                goal_id=goal.id,
                status="released",
                    target_window_start="now",
                    target_window_end="now",
                    queue_position=0,
                )

        # 构造 DeferredTask
        task = DeferredTask(
            id=goal.id,
            goal_description=goal.description,
            priority=getattr(goal, "priority", "NORMAL"),
            provider=provider,
            estimated_tokens=avg_tokens,
            estimated_duration_seconds=avg_duration,
            target_window_start=window.starts_at_iso,
            target_window_end=window.ends_at_iso,
            status="queued",
            created_at=now.isoformat(),
            goal_json=goal.model_dump_json(),
        )
        position = await self._queue.push(task)

        logger.info(
            "goal_enqueued_offpeak",
            goal_id=goal.id,
            provider=provider,
            target_window=task.target_window_start,
            position=position,
        )
        return EnqueueResult(
            goal_id=goal.id,
            status="queued",
            target_window_start=task.target_window_start,
            target_window_end=task.target_window_end,
            queue_position=position,
        )

    async def start(self) -> None:
        """启动后台窗口监视协程。

        恢复数据库中处于 released/running 状态的僵尸任务
        （上次关闭时窗口已释放但未完成的）。
        """
        # 恢复僵尸任务
        released = await self._queue.list_all("released")
        for task in released:
            await self._queue.mark_cancelled(task.id)
            logger.warning("zombie_task_cleaned", goal_id=task.id, reason="stale_released_on_restart")

        self._watcher_task = asyncio.create_task(self._window_watcher())
        logger.info("offpeak_scheduler_started", watcher_interval=self._watcher_interval)

    async def stop(self) -> None:
        """停止 watcher 协程。"""
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

    @property
    def force_offpeak_only(self) -> bool:
        return self._force_offpeak_only

    # ── 后台协程 ──

    async def _window_watcher(self) -> None:
        """后台协程: 按可配置间隔检查低峰窗口。

        WHY 可配置间隔: 生产环境可能需要更频繁检查（30s），
        开发环境默认 60s 足够。
        """
        while True:
            try:
                await self._check_windows()
            except Exception:
                logger.exception("window_watcher_error")
            await asyncio.sleep(self._watcher_interval)

    async def _check_windows(self) -> None:
        """检查所有活跃厂商的低峰窗口——释放到期任务。"""
        now = datetime.now(UTC)

        for provider in self._peak.providers:
            # 查找所有 queued 任务的目标窗口
            all_queued = await self._queue.list_all("queued")
            provider_tasks = [t for t in all_queued if t.provider == provider]
            if not provider_tasks:
                continue

            # 按目标窗口分桶
            windows: dict[str, list[DeferredTask]] = {}
            for task in provider_tasks:
                key = task.target_window_start
                if key not in windows:
                    windows[key] = []
                windows[key].append(task)

            for window_start_iso, tasks in windows.items():
                try:
                    window_start = datetime.fromisoformat(window_start_iso)
                except (ValueError, TypeError):
                    continue

                # 窗口结束后 30 分钟仍未释放 → 跳过（可能是过期窗口）
                minutes_since_start = (now - window_start).total_seconds() / 60
                if minutes_since_start < 0:
                    continue  # 窗口还没到

                # 取第一个任务的 target_window_end
                window_end_iso = tasks[0].target_window_end
                try:
                    window_end = datetime.fromisoformat(window_end_iso)
                except (ValueError, TypeError):
                    window_end = window_start + timedelta(hours=10)

                # 窗口已结束 >30min → 跳过，任务标记为过期
                if now > window_end + timedelta(minutes=30):
                    for task in tasks:
                        await self._queue.mark_cancelled(task.id)
                        logger.warning(
                            "window_expired_task_cancelled",
                            goal_id=task.id,
                            window_start=window_start_iso,
                        )
                    continue

                # 窗口正在运行中 → 计算容量并释放
                if now >= window_start:
                    capacity = estimate_window_capacity(window_start, window_end, tasks)
                    if capacity > 0:
                        released = await self._queue.pop_for_window(
                            window_start_iso, window_end_iso, limit=capacity
                        )
                        for task in released:
                            try:
                                from orbit.goal.models import GoalSession
                                goal = GoalSession.model_validate_json(task.goal_json)
                                bg = asyncio.create_task(self._orch.run(goal))
                                bg.add_done_callback(
                                    lambda t, dt=task: asyncio.ensure_future(
                                        self._on_task_done(t, dt)
                                    )
                                )
                                logger.info(
                                    "offpeak_task_released",
                                    goal_id=task.id,
                                    provider=provider,
                                )
                            except Exception:
                                logger.exception(
                                    "offpeak_task_release_failed",
                                    goal_id=task.id,
                                )

                # 窗口结束前 10 分钟: 容量不够则顺延
                minutes_to_end = (window_end - now).total_seconds() / 60
                if 0 < minutes_to_end <= 10:
                    capacity = estimate_window_capacity(now, window_end, tasks)
                    if capacity < len(tasks):
                        next_window = self._peak.next_offpeak_window(provider, after=window_end)
                        if next_window:
                            overflow = tasks[capacity:]
                            for task in overflow:
                                await self._queue.reschedule(
                                    task.id,
                                    next_window.starts_at_iso,
                                    next_window.ends_at_iso,
                                )
                            logger.warning(
                                "window_overflow_rescheduled",
                                provider=provider,
                                overflow_count=len(overflow),
                            )

    async def _on_task_done(
        self, t: asyncio.Task, deferred_task: DeferredTask
    ) -> None:
        """Goal 执行完毕回调——记录实际消耗和成本节省。"""
        try:
            result = t.result()
            # 计算成本节省
            provider = deferred_task.provider
            peak_price = self._peak.get_price_multiplier(provider) if self._peak.is_peak(provider) else 1.0
            offpeak_price = self._peak.get_price_multiplier(provider)
            # 简化: 用 1K tokens 基础价格 × 倍数 × tokens
            from orbit.gateway.routing import _MODEL_COSTS
            base_price = _MODEL_COSTS.get(provider, 0.001)
            peak_cost = deferred_task.estimated_tokens / 1000 * base_price * peak_price
            offpeak_cost = deferred_task.estimated_tokens / 1000 * base_price * offpeak_price
            saved = round(max(0, peak_cost - offpeak_cost), 4)

            await self._queue.mark_done(
                deferred_task.id,
                actual_tokens=getattr(result, "total_tokens", 0),
                cost_saved=saved,
            )
        except Exception:
            logger.exception("task_done_callback_failed", goal_id=deferred_task.id)
