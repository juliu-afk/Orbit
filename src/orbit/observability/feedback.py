"""审计数据飞轮——轨迹分析→调优建议 (Phase B 遗留收尾 US3).

WHY 存在:
  TrajectoryCollector 收集了结构化轨迹数据，但没有闭环反馈。
  FeedbackEngine 周期性分析失败率/误判率/效率指标，
  输出改进建议 JSON——人工审查后应用，不自动修改参数。

设计:
  - 读取 TrajectoryCollector 的完成/失败轨迹
  - 三类分析: 失败率、误判率(DRIFTED/REPEATED)、效率(avg_turns/tool_calls)
  - 与上次分析对比(基线存 feedback_results 表)
  - 生成 Recommendation 列表，含 confidence 评分
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class FeedbackMetrics(BaseModel):
    """反馈分析指标."""

    total_trajectories: int = 0
    completed_count: int = 0
    failed_count: int = 0
    success_rate: float = 0.0           # completed / total
    avg_turns: float = 0.0
    avg_tool_calls: float = 0.0
    avg_duration_ms: float = 0.0
    drift_rate: float = 0.0             # DRIFTED steps / total steps
    repeat_rate: float = 0.0            # REPEATED steps / total steps
    top_error_messages: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """单条改进建议."""

    category: str = ""                  # "prompt" | "threshold" | "scheduling" | "tool"
    severity: str = ""                  # "high" | "medium" | "low"
    confidence: float = 0.0             # 0.0-1.0
    description: str = ""               # 人类可读描述
    evidence: str = ""                  # 数据支撑


class FeedbackReport(BaseModel):
    """一次反馈分析报告."""

    generated_at: str = ""              # ISO 8601
    period_start: float = 0.0           # unix timestamp
    period_end: float = 0.0
    metrics: FeedbackMetrics = Field(default_factory=FeedbackMetrics)
    recommendations: list[Recommendation] = Field(default_factory=list)
    # 与上次对比
    previous_success_rate: float | None = None
    trend: str = ""                     # "improving" | "declining" | "stable" | "baseline"


class FeedbackEngine:
    """审计反馈引擎——分析轨迹数据，生成改进建议.

    用法:
        engine = FeedbackEngine("trajectories.db")
        report = await engine.analyze()
        # → FeedbackReport with metrics + recommendations
    """

    # 分析阈值
    MIN_TRAJECTORIES = 5                # 最少轨迹数才触发分析
    HIGH_FAILURE_THRESHOLD = 0.15       # 失败率 >15% → 告警
    HIGH_DRIFT_THRESHOLD = 0.10         # 漂移率 >10% → 告警
    HIGH_REPEAT_THRESHOLD = 0.08        # 重复率 >8% → 告警
    LONG_TURNS_THRESHOLD = 20           # 平均轮数 >20 → 告警

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS feedback_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        generated_at TEXT NOT NULL,
        report_json TEXT NOT NULL,
        period_start REAL NOT NULL,
        period_end REAL NOT NULL
    );
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path

    # ── 公开接口 ─────────────────────────────────

    async def analyze(self) -> FeedbackReport | None:
        """分析轨迹数据，生成反馈报告.

        Returns:
            FeedbackReport 如果有足够数据，否则 None.
        """
        collector = _open_collector(self._db_path)
        try:
            completed = collector.get_completed(limit=100)
            failed = collector.get_failed(limit=50)

            total = len(completed) + len(failed)
            if total < self.MIN_TRAJECTORIES:
                return None

            # 计算指标
            metrics = self._compute_metrics(completed, failed)

            # 读上次报告做趋势对比
            previous = await self.get_last_report()
            prev_sr = previous.metrics.success_rate if previous else None

            # 生成建议
            recommendations = self._generate_recommendations(metrics, prev_sr)

            # 趋势判定
            trend = self._determine_trend(metrics.success_rate, prev_sr)

            now = time.time()
            report = FeedbackReport(
                generated_at=datetime.now(timezone.utc).isoformat(),
                period_start=_earliest_time(completed + failed),
                period_end=now,
                metrics=metrics,
                recommendations=recommendations,
                previous_success_rate=prev_sr,
                trend=trend,
            )

            # 持久化
            self._save_report(report)
            return report
        finally:
            collector.close()

    async def get_last_report(self) -> FeedbackReport | None:
        """读取最近一次分析报告."""
        db = sqlite3.connect(self._db_path)
        db.execute(self.SCHEMA_SQL)
        row = db.execute(
            "SELECT report_json FROM feedback_results ORDER BY id DESC LIMIT 1"
        ).fetchone()
        db.close()

        if row is None:
            return None
        return FeedbackReport.model_validate(json.loads(row[0]))

    # ── 内部方法 ─────────────────────────────────

    def _compute_metrics(
        self, completed: list[dict], failed: list[dict]
    ) -> FeedbackMetrics:
        """从轨迹列表计算聚合指标."""
        all_trajs = completed + failed
        total = len(all_trajs)
        completed_count = len(completed)
        failed_count = len(failed)

        # 聚合 steps
        total_steps = 0
        drifted_steps = 0
        repeated_steps = 0
        total_duration = 0.0
        total_turns = 0
        total_tool_calls = 0
        error_counts: dict[str, int] = {}

        for traj in all_trajs:
            total_turns += traj.get("total_turns", 0)
            total_tool_calls += traj.get("total_tool_calls", 0)

        for traj in all_trajs:
            steps = traj.get("steps", [])
            for step in steps:
                total_steps += 1
                outcome = step.get("outcome", "")
                if outcome == "drifted":
                    drifted_steps += 1
                elif outcome == "repeated":
                    repeated_steps += 1
                total_duration += step.get("duration_ms", 0)
                err = step.get("error_message", "")
                if err:
                    error_counts[err] = error_counts.get(err, 0) + 1

        # top 3 错误
        top_errors = sorted(
            error_counts.items(), key=lambda x: x[1], reverse=True
        )[:3]

        return FeedbackMetrics(
            total_trajectories=total,
            completed_count=completed_count,
            failed_count=failed_count,
            success_rate=completed_count / total if total > 0 else 0.0,
            avg_turns=total_turns / total if total > 0 else 0.0,
            avg_tool_calls=total_tool_calls / total if total > 0 else 0.0,
            avg_duration_ms=total_duration / total_steps if total_steps > 0 else 0.0,
            drift_rate=drifted_steps / total_steps if total_steps > 0 else 0.0,
            repeat_rate=repeated_steps / total_steps if total_steps > 0 else 0.0,
            top_error_messages=[e for e, _ in top_errors],
        )

    def _generate_recommendations(
        self, m: FeedbackMetrics, prev_success_rate: float | None
    ) -> list[Recommendation]:
        """根据指标生成改进建议."""
        recs: list[Recommendation] = []

        # 失败率高 → prompt/scheduling 建议
        if m.success_rate < (1.0 - self.HIGH_FAILURE_THRESHOLD):
            recs.append(Recommendation(
                category="prompt",
                severity="high",
                confidence=min(0.9, 1.0 - m.success_rate + 0.2),
                description=(
                    f"失败率 {m.failed_count}/{m.total_trajectories} "
                    f"({(1 - m.success_rate) * 100:.1f}%)，建议审查 Agent Prompt——"
                    f"主要错误: {', '.join(m.top_error_messages[:2]) if m.top_error_messages else '无具体错误信息'}"
                ),
                evidence=f"top errors: {m.top_error_messages}",
            ))

        # 漂移率高 → prompt/threshold 建议
        if m.drift_rate > self.HIGH_DRIFT_THRESHOLD:
            recs.append(Recommendation(
                category="threshold",
                severity="medium",
                confidence=min(0.85, m.drift_rate * 5 + 0.3),
                description=(
                    f"漂移率 {m.drift_rate * 100:.1f}%——ReflAct 检出的偏离比例偏高，"
                    f"建议收紧 Monitor 的 drift_weight_threshold 或审查 Agent 理解目标的能力"
                ),
                evidence=f"drift_rate={m.drift_rate:.3f}, threshold={self.HIGH_DRIFT_THRESHOLD}",
            ))

        # 重复率高 → tool/scheduling 建议
        if m.repeat_rate > self.HIGH_REPEAT_THRESHOLD:
            recs.append(Recommendation(
                category="tool",
                severity="medium",
                confidence=min(0.85, m.repeat_rate * 5 + 0.3),
                description=(
                    f"重复率 {m.repeat_rate * 100:.1f}%——Agent 频繁重复相同操作，"
                    f"建议检查工具返回内容是否清晰、是否缺少幂等检查"
                ),
                evidence=f"repeat_rate={m.repeat_rate:.3f}, threshold={self.HIGH_REPEAT_THRESHOLD}",
            ))

        # 平均轮数过高 → scheduling 建议
        if m.avg_turns > self.LONG_TURNS_THRESHOLD:
            recs.append(Recommendation(
                category="scheduling",
                severity="low",
                confidence=min(0.8, m.avg_turns / 30),
                description=(
                    f"平均 {m.avg_turns:.1f} 轮/任务，建议拆分子任务以降低单任务复杂度"
                ),
                evidence=f"avg_turns={m.avg_turns:.1f}, threshold={self.LONG_TURNS_THRESHOLD}",
            ))

        # 趋势恶化 → 综合建议
        if prev_success_rate is not None and m.success_rate < prev_success_rate - 0.05:
            recs.append(Recommendation(
                category="scheduling",
                severity="medium",
                confidence=0.7,
                description=(
                    f"成功率从 {prev_success_rate * 100:.1f}% 降至 {m.success_rate * 100:.1f}%，"
                    f"建议审查最近代码变更是否引入新问题"
                ),
                evidence=f"success_rate: {prev_success_rate:.2%} → {m.success_rate:.2%}",
            ))

        return recs

    @staticmethod
    def _determine_trend(current: float, previous: float | None) -> str:
        if previous is None:
            return "baseline"
        diff = current - previous
        if diff > 0.03:
            return "improving"
        elif diff < -0.03:
            return "declining"
        return "stable"

    def _save_report(self, report: FeedbackReport) -> None:
        db = sqlite3.connect(self._db_path)
        db.execute(self.SCHEMA_SQL)
        db.execute(
            "INSERT INTO feedback_results (generated_at, report_json, period_start, period_end) "
            "VALUES (?, ?, ?, ?)",
            (
                report.generated_at,
                report.model_dump_json(),
                report.period_start,
                report.period_end,
            ),
        )
        db.commit()
        db.close()


# ── 内部辅助 ─────────────────────────────────────

def _open_collector(db_path: str):
    """打开 TrajectoryCollector（延迟导入避免循环依赖）."""
    from orbit.observability.trajectory import TrajectoryCollector

    return TrajectoryCollector(db_path=db_path)


def _earliest_time(trajs: list[dict]) -> float:
    earliest = float("inf")
    for t in trajs:
        started = t.get("started_at", float("inf"))
        if started and started < earliest:
            earliest = started
    return earliest if earliest != float("inf") else time.time() - 86400
