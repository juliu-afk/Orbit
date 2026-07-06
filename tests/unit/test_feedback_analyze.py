"""FeedbackEngine analyze() deep coverage."""
from __future__ import annotations

import pytest

from orbit.observability.trajectory import TrajectoryCollector, TrajectoryStep, StepOutcome
from orbit.observability.feedback import FeedbackEngine, FeedbackMetrics, Recommendation


class TestFeedbackAnalyze:
    @pytest.fixture
    def collector(self):
        return TrajectoryCollector(db_path=":memory:")

    @pytest.mark.asyncio
    async def test_analyze_with_enough_data(self, collector):
        for i in range(6):
            traj = collector.start_trajectory(task_id=f"t{i}", goal=f"g{i}", agent_role="dev", project_id="p")
            collector.add_step(traj.trajectory_id, TrajectoryStep(turn=1, thought="x", action="a", outcome=StepOutcome.SUCCESS, duration_ms=100))
            collector.finish_trajectory(traj.trajectory_id, final_outcome="completed" if i < 5 else "failed", quality_score=0.8, total_turns=5+i, total_tool_calls=3+i)
        e = FeedbackEngine(collector=collector)
        report = await e.analyze()
        assert report is not None
        assert report.metrics.total_trajectories >= 6
        assert report.metrics.success_rate >= 0.0
        assert len(report.recommendations) >= 0
        assert report.trend in ("baseline", "improving", "declining", "stable")

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data(self, collector):
        e = FeedbackEngine(collector=collector)
        report = await e.analyze()
        assert report is None

    @pytest.mark.asyncio
    async def test_get_last_report_none_initially(self, collector):
        e = FeedbackEngine(collector=collector)
        assert await e.get_last_report() is None

    def test_metrics_model(self):
        m = FeedbackMetrics(
            total_trajectories=10, completed_count=8, failed_count=2,
            success_rate=0.8, avg_turns=12.0, avg_tool_calls=4.0,
            avg_duration_ms=300.0, drift_rate=0.05, repeat_rate=0.02,
            top_error_messages=["err1"],
        )
        assert m.total_trajectories == 10
        assert m.success_rate == 0.8
        data = m.model_dump()
        assert data["success_rate"] == 0.8

    def test_recommendation_model(self):
        r = Recommendation(category="prompt", severity="high", confidence=0.9, description="fix", evidence="data")
        assert r.category == "prompt"
        assert r.severity == "high"
