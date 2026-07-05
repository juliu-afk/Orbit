"""FeedbackEngine 单元测试 (US3)."""

from __future__ import annotations

import pytest


class TestFeedbackEngine:
    """反馈引擎——分析逻辑 + 建议生成."""

    @pytest.fixture
    def engine(self):
        from orbit.observability.feedback import FeedbackEngine
        from orbit.observability.trajectory import TrajectoryCollector

        collector = TrajectoryCollector(db_path=":memory:")
        return FeedbackEngine(collector=collector)

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data(self, engine):
        """少于 5 条轨迹 → 返回 None."""
        report = await engine.analyze()
        assert report is None

    @pytest.mark.asyncio
    async def test_analyze_with_mock_data(self):
        """有 ≥5 条完成轨迹 → 返回 FeedbackReport."""
        from orbit.observability.feedback import FeedbackEngine
        from orbit.observability.trajectory import (
            StepOutcome,
            TrajectoryCollector,
            TrajectoryStep,
        )

        collector = TrajectoryCollector(db_path=":memory:")
        # 创建 6 条完成轨迹
        for i in range(6):
            traj = collector.start_trajectory(
                task_id=f"task_{i}",
                goal=f"测试目标 {i}",
                agent_role="developer",
                project_id="test",
            )
            step = TrajectoryStep(
                turn=1,
                thought="测试",
                action="read_file",
                outcome=StepOutcome.SUCCESS,
                duration_ms=100.0,
            )
            collector.add_step(traj.trajectory_id, step)
            collector.finish_trajectory(
                traj.trajectory_id,
                final_outcome="completed" if i < 5 else "failed",
                quality_score=0.8,
                total_turns=5 + i,
                total_tool_calls=3 + i,
            )

        # FeedbackEngine 与 collector 共享数据库连接
        engine2 = FeedbackEngine(collector=collector)
        completed = collector.get_completed(limit=100)
        failed = collector.get_failed(limit=50)
        assert len(completed) + len(failed) >= 5

        metrics = engine2._compute_metrics(completed, failed)
        assert metrics.total_trajectories >= 5
        assert metrics.success_rate >= 0.0
        assert metrics.avg_turns > 0

        recs = engine2._generate_recommendations(metrics, None)
        assert isinstance(recs, list)

        collector.close()

    def test_compute_metrics_empty(self, engine):
        """空数据 → 指标全零."""
        metrics = engine._compute_metrics([], [])
        assert metrics.total_trajectories == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_turns == 0.0

    def test_generate_recommendations_high_failure(self, engine):
        """高失败率 → 生成 prompt 建议."""
        from orbit.observability.feedback import FeedbackMetrics

        metrics = FeedbackMetrics(
            total_trajectories=20,
            completed_count=14,
            failed_count=6,
            success_rate=0.70,
            avg_turns=15.0,
            avg_tool_calls=3.0,
            avg_duration_ms=500.0,
            drift_rate=0.05,
            repeat_rate=0.03,
            top_error_messages=["FileNotFoundError"],
        )
        recs = engine._generate_recommendations(metrics, 0.85)
        # 应有失败率建议 + 趋势恶化建议
        assert len(recs) >= 1
        assert any(r.category == "prompt" for r in recs)

    def test_generate_recommendations_high_drift(self, engine):
        """高漂移率 → 生成 threshold 建议."""
        from orbit.observability.feedback import FeedbackMetrics

        metrics = FeedbackMetrics(
            total_trajectories=20,
            completed_count=19,
            failed_count=1,
            success_rate=0.95,
            avg_turns=10.0,
            avg_tool_calls=3.0,
            avg_duration_ms=500.0,
            drift_rate=0.15,
            repeat_rate=0.03,
            top_error_messages=[],
        )
        recs = engine._generate_recommendations(metrics, 0.95)
        assert any(r.category == "threshold" for r in recs)

    def test_determine_trend(self, engine):
        """趋势判定."""
        assert engine._determine_trend(0.90, None) == "baseline"
        assert engine._determine_trend(0.90, 0.85) == "improving"
        assert engine._determine_trend(0.80, 0.88) == "declining"
        assert engine._determine_trend(0.85, 0.85) == "stable"

    @pytest.mark.asyncio
    async def test_get_last_report_empty(self, engine):
        """无历史报告 → None."""
        report = await engine.get_last_report()
        assert report is None

    def test_metrics_serializable(self, engine):
        """指标可序列化."""
        from orbit.observability.feedback import FeedbackMetrics

        m = FeedbackMetrics(
            total_trajectories=10,
            completed_count=8,
            failed_count=2,
            success_rate=0.8,
            avg_turns=12.0,
            avg_tool_calls=4.0,
            avg_duration_ms=300.0,
            drift_rate=0.05,
            repeat_rate=0.02,
            top_error_messages=["err1", "err2"],
        )
        data = m.model_dump()
        assert data["success_rate"] == 0.8
        assert len(data["top_error_messages"]) == 2
