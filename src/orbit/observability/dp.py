"""差分隐私审计 (V14.2+Theory 方向10).

(ε,δ)-DP: Laplace噪声加至聚合统计量.
ε=1→单个项目从报告中移除/加入,输出概率分布变化≤e¹倍.

用法:
    dp = DPGuard(epsilon=1.0)
    safe_count = dp.laplace_mech(true_count, sensitivity=1)
"""
from __future__ import annotations
import math
import random


class DPGuard:
    """差分隐私保护——跨项目反馈报告的隐私保证."""

    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5):
        self.epsilon = epsilon
        self.delta = delta

    def laplace_mech(self, value: float, sensitivity: float = 1.0) -> float:
        """Laplace机制——返回加噪后的值."""
        scale = sensitivity / self.epsilon
        noise = random.uniform(-1, 1)
        # Laplace分布: sign*log(1-2|u|)*scale
        noise = math.copysign(1, noise) * math.log(1 - 2 * abs(noise)) * scale
        return value + noise

    def gaussian_mech(self, value: float, sensitivity: float = 1.0) -> float:
        """Gaussian机制——(ε,δ)-DP."""
        sigma = math.sqrt(2 * math.log(1.25 / self.delta)) * sensitivity / self.epsilon
        return value + random.gauss(0, sigma)

    def privatize_report(self, metrics: dict[str, float],
                         sensitivity: float = 1.0) -> dict[str, float]:
        """对报告的所有数值指标加DP噪声."""
        return {k: self.laplace_mech(v, sensitivity) for k, v in metrics.items()}
