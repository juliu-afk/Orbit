"""拜占庭容错 (V14.2+Theory 方向25).

n > 3f 必要且充分——n=4容忍f=1拜占庭故障.
关键操作(DROP/TRUNCATE/eval/exec/rm)→BFT共识门禁.

用法:
    guard = BFTGuard(n_agents=4)
    ok = guard.approve("DROP TABLE users")
"""
from __future__ import annotations

# 需要共识的关键操作
_DESTRUCTIVE_PATTERNS = [
    "DROP", "TRUNCATE", "DELETE FROM", "ALTER TABLE",
    "eval(", "exec(", "rm -rf", "rmdir", "DEL /F",
    "os.remove", "shutil.rmtree", "__import__",
]


class BFTGuard:
    """拜占庭容错守卫——关键操作需多数共识."""

    def __init__(self, n_agents: int = 4):
        self.n = n_agents
        self.f = (n_agents - 1) // 3  # n>3f→max f
        self.quorum = 2 * self.f + 1   # 需要的共识票数

    def is_destructive(self, action: str) -> bool:
        """检查操作是否需要BFT共识."""
        action_upper = action.upper()
        return any(p.upper() in action_upper for p in _DESTRUCTIVE_PATTERNS)

    def approve(self, action: str, votes: list[bool] | None = None) -> tuple[bool, str]:
        """BFT共识——n个Agent投票,需≥quorum同意.

        votes=None→默认所有Agent同意(模拟)
        """
        if not self.is_destructive(action):
            return (True, "非破坏性操作——无需共识")
        if votes is None:
            votes = [True] * self.n
        yes = sum(1 for v in votes if v)
        if yes >= self.quorum:
            return (True, f"BFT通过({yes}/{self.n}≥{self.quorum})")
        return (False, f"BFT拒绝({yes}/{self.n}<{self.quorum})——可能{self.f}个拜占庭故障")

    @property
    def fault_tolerance(self) -> int:
        return self.f
