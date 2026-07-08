"""自由能原理 (V14.2+Theory 方向15).

F = D_KL[q(θ)||p(θ)] - E_q[ln p(o|θ)] = 复杂度 - 准确性
Monitor/GEPA/SCOPE/Reflection统一为ΔF最小化.

用法:
    fe = FreeEnergyMonitor()
    delta_F = fe.compute(surprise, complexity)
"""
from __future__ import annotations
import math


class FreeEnergyMonitor:
    """变分自由能监控——统一三元组."""

    def __init__(self, tau: float = 0.5):
        self.tau = tau  # 惊奇阈值

    def compute(self, surprise: float, complexity: float,
                accuracy: float) -> float:
        """F = complexity - accuracy.

        surprise = -ln p(o|θ)（观察惊奇度）
        complexity = D_KL(q||p)（模型复杂度）
        accuracy = E_q[ln p(o|θ)]（预测准确度）
        """
        return complexity - accuracy

    def is_critical(self, free_energy: float) -> bool:
        """ΔF > τ → CRITICAL."""
        return free_energy > self.tau

    def guidance(self, free_energy: float) -> str:
        """ΔF驱动的自适应矫正建议."""
        if free_energy < 0.1:
            return ""  # 在稳态——无需干预
        elif free_energy < self.tau:
            return "轻微惊奇——调整预测模型"
        elif free_energy < self.tau * 2:
            return "显著惊奇——触发VIGIL heal"
        else:
            return "严重惊奇——升级人工决策"

    @staticmethod
    def estimate_from_alerts(drift_score: float, repetition_count: int,
                             latency_ms: float) -> float:
        """从Monitor告警估算自由能增量."""
        F = 0.3 * drift_score + 0.3 * min(repetition_count / 10.0, 1.0)
        if latency_ms > 5000:
            F += 0.2
        return F
