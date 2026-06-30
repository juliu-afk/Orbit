"""编辑摇摆检测——业务层减熵 P1.

追踪文件变更历史 → 检测高熵模式 → 触发需求重确认。
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger("orbit.edit_stability")


@dataclass
class FileEditRecord:
    """单次编辑记录."""

    file_path: str
    agent_id: str = ""
    # P0: 统一用 UTC-aware datetime，避免 aware/naive 比较 TypeError
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    changed_functions: list[str] = field(default_factory=list)


@dataclass
class StabilityReport:
    """编辑稳定性报告."""

    file_path: str
    edit_count: int  # 7 天内编辑次数
    has_ping_pong: bool = False  # 存在回弹模式
    conflicting_agents: list[str] = field(default_factory=list)
    is_high_entropy: bool = False
    suggestion: str = ""


class EditStabilityDetector:
    """编辑摇摆检测器——基于内存记录的轻量实现.

    阈值:
    - HIGH_ENTROPY_THRESHOLD = 4  (7天内 ≥4 次编辑)
    - PING_PONG_THRESHOLD = 2     (同样逻辑改回 ≥2 次)
    - AGENT_CONFLICT_THRESHOLD = 3  (≥3 个 Agent 编辑同一文件)
    """

    HIGH_ENTROPY_THRESHOLD = 4
    PING_PONG_THRESHOLD = 2
    AGENT_CONFLICT_THRESHOLD = 3
    LOOKBACK_DAYS = 7
# P2-2: 全局历史文件硬上限——防止长期运行内存泄漏
    MAX_HISTORY_FILES = 5000
    # P2: 超限 cooldown——每 CLEANUP_COOLDOWN 次 edit 才清一次
    CLEANUP_COOLDOWN = 50

    def __init__(self) -> None:
        self._history: dict[str, list[FileEditRecord]] = {}
        # P1: threading.Lock——保护 record_edit + cleanup 并发，保持 sync 签名
        self._lock = threading.Lock()
        self._edit_since_cleanup = 0

    def record_edit(
        self, file_path: str, agent_id: str = "", changed_functions: list[str] | None = None
    ) -> None:
        """记录一次文件编辑——线程安全."""
        record = FileEditRecord(
            file_path=file_path,
            agent_id=agent_id,
            changed_functions=changed_functions or [],
        )
        with self._lock:
            if file_path not in self._history:
                self._history[file_path] = []
            self._history[file_path].append(record)

            # 裁剪——只保留 LOOKBACK_DAYS 内的记录
            cutoff = datetime.now(UTC) - timedelta(days=self.LOOKBACK_DAYS)
            self._history[file_path] = [r for r in self._history[file_path] if r.timestamp > cutoff]

            # P2-2: 全局清理——cooldown + 缓冲
            self._edit_since_cleanup += 1
            if (
                len(self._history) > self.MAX_HISTORY_FILES
                and self._edit_since_cleanup >= self.CLEANUP_COOLDOWN
            ):
                self._cleanup_stale()
                self._edit_since_cleanup = 0

    def check(self, file_path: str) -> StabilityReport:
        """检查文件的编辑稳定性."""
        records = self._history.get(file_path, [])
        report = StabilityReport(file_path=file_path, edit_count=len(records))

        if len(records) < self.HIGH_ENTROPY_THRESHOLD:
            return report

        report.is_high_entropy = True
        issues: list[str] = []

        # 检测 1: 编辑次数过多
        issues.append(f"近 {self.LOOKBACK_DAYS} 天编辑 {len(records)} 次")

        # 检测 2: 回弹模式——同样函数反复修改
        func_edits: dict[str, list[str]] = {}
        for r in records:
            for func in r.changed_functions:
                if func not in func_edits:
                    func_edits[func] = []
                func_edits[func].append(r.agent_id)

        for func_name, agents in func_edits.items():
            if len(agents) >= self.PING_PONG_THRESHOLD:
                report.has_ping_pong = True
                issues.append(f"函数 {func_name} 存在回弹模式")

        # 检测 3: 多 Agent 竞争
        agent_counts = Counter(r.agent_id for r in records if r.agent_id)
        if len(agent_counts) >= self.AGENT_CONFLICT_THRESHOLD:
            report.conflicting_agents = list(agent_counts.keys())
            issues.append(f"{len(agent_counts)} 个 Agent 编辑此文件")

        if issues:
            report.suggestion = "建议重新确认需求：" + "；".join(issues)

        return report

    def get_high_entropy_files(self) -> list[StabilityReport]:
        """返回所有高熵文件的报告."""
        reports: list[StabilityReport] = []
        for path in self._history:
            report = self.check(path)
            if report.is_high_entropy:
                reports.append(report)
        return reports

    # ── 内部 ────────────────────────────────────────────

    def _cleanup_stale(self) -> None:
        """P2-2: 删除空记录文件，若仍超限删除到 90% 容量."""
        # 删除空记录
        empty = [k for k, v in self._history.items() if not v]
        for k in empty:
            del self._history[k]
        # 仍超限——按最后编辑时间排序，删到 90% 容量
        target = int(self.MAX_HISTORY_FILES * 0.9)
        if len(self._history) > self.MAX_HISTORY_FILES:
            sorted_files = sorted(
                self._history.items(),
                key=lambda kv: max(
                    (r.timestamp for r in kv[1]),
                    default=datetime(2000, 1, 1, tzinfo=UTC),
                ),
            )
            remove_count = len(sorted_files) - target
            for k, _ in sorted_files[:remove_count]:
                del self._history[k]
