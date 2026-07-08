"""PAC 泛化边界 (V14.2+Theory 方向14).

ε = √((ln|H| + ln(1/δ)) / (2m))
|H| = 原则库大小, m = 评估样本数, δ = 置信度

界宽时自动建议更多数据——替代硬编码 UPGRADE_THRESHOLD=3.

用法:
    bound = PACBound()
    eps = bound.compute(H_size=50, m_samples=100)
    if not bound.is_reliable(H_size=50, m=100):
        print("Need more evaluation data")
"""
from __future__ import annotations
import math


class PACBound:
    """Probably Approximately Correct 泛化误差上界."""

    def __init__(self, delta: float = 0.05):
        self.delta = delta

    def compute(self, H_size: int, m_samples: int) -> float:
        """计算泛化误差上界 ε."""
        if m_samples < 1 or H_size < 1:
            return 1.0
        return math.sqrt(
            (math.log(H_size) + math.log(1.0 / self.delta)) / (2.0 * m_samples)
        )

    def is_reliable(self, H_size: int, m: int, min_epsilon: float = 0.3) -> bool:
        """是否可靠——界 < min_epsilon 表示泛化可接受."""
        return self.compute(H_size, m) < min_epsilon

    def min_samples_for(self, H_size: int, target_epsilon: float = 0.3) -> int:
        """达到目标泛化界所需最少样本数."""
        return math.ceil(
            (math.log(H_size) + math.log(1.0 / self.delta)) / (2.0 * target_epsilon ** 2)
        )

    def adaptive_threshold(self, H_size: int, m_samples: int,
                           base_threshold: int = 3) -> int:
        """PAC 指导的自适应阈值——替代 SCOPE UPGRADE_THRESHOLD=3.

        样本少→阈值高(需要更多重复才可信), 样本多→阈值低(泛化保证强).
        """
        eps = self.compute(H_size, m_samples)
        if eps > 0.5:
            return base_threshold * 3
        elif eps > 0.3:
            return base_threshold * 2
        else:
            return max(base_threshold - 1, 1)
