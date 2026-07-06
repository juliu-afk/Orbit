"""PeakWindowManager——高峰/低峰时段判定。

从 offpeak_scheduler.py 拆分。DeferredQueue 见 deferred_queue.py，
OffPeakScheduler 见 scheduler.py。

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
from typing import Any, TYPE_CHECKING, cast, get_args

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


