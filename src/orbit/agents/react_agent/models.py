class IterationBudget:
    """迭代预算——对标 Hermes iteration_budget.

    WHY 独立类: 预算消耗逻辑与循环逻辑分离，方便测试。
    """

    def __init__(self, total: int = 90) -> None:
        self.total = total
        self._consumed = 0

    def consume(self, n: int = 1) -> bool:
        """消耗 n 个预算单位。返回是否还有剩余。"""
        self._consumed += n
        return self._consumed <= self.total

    @property
    def remaining(self) -> int:
        return max(0, self.total - self._consumed)

