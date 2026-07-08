"""差分隐私审计 (V14.2+Theory 方向10). P0修复: uniform(-0.5,0.5)防log负数."""
from __future__ import annotations
import math
import random

class DPGuard:
    def __init__(self, epsilon: float = 1.0, delta: float = 1e-5):
        self.epsilon = epsilon
        self.delta = max(delta, 1e-12)  # P2-4: delta下界

    def laplace_mech(self, value: float, sensitivity: float = 1.0) -> float:
        """Laplace机制——使用逆CDF, u ∈ (-0.5, 0.5). P0修复."""
        scale = sensitivity / self.epsilon
        u = random.uniform(-0.5, 0.5)
        noise = math.copysign(1, u) * math.log(1 - 2 * abs(u)) * scale
        return value + noise

    def gaussian_mech(self, value: float, sensitivity: float = 1.0) -> float:
        sigma = math.sqrt(2 * math.log(1.25 / self.delta)) * sensitivity / self.epsilon
        return value + random.gauss(0, sigma)

    def privatize_report(self, metrics: dict[str, float], sensitivity: float = 1.0) -> dict:
        return {k: self.laplace_mech(v, sensitivity) for k, v in metrics.items()}
