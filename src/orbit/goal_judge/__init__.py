"""Goal Judge——目标达成判定模型。

对标 MiMo Code session/goal.ts ~150行。
Verdict schema + fail-open + MAX_GOAL_REACT 硬上限。
"""

from orbit.goal_judge.judge import GoalJudge
from orbit.goal_judge.models import Goal, Verdict

__all__ = [
    "Goal",
    "GoalJudge",
    "Verdict",
]
