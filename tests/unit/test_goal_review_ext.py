import pytest
class TestGoalIntake:
    def test_router(self):
        from orbit.goal.intake_router import IntakeRouter
        assert IntakeRouter() is not None
class TestGoalJudge:
    def test_init(self):
        from orbit.goal_judge.judge import GoalJudge
        assert GoalJudge() is not None
class TestReviewProgressive:
    def test_init(self):
        from orbit.review.progressive import ProgressiveReviewer
        assert ProgressiveReviewer() is not None
class TestReviewPonytail:
    def test_init(self):
        from orbit.review.ponytail import PonytailReviewer
        assert PonytailReviewer() is not None
