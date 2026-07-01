from orbit.goal_judge.judge import GoalJudge
def test_judge_init():
    j = GoalJudge()
    assert j is not None
