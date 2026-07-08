"""信息几何 (V14.2+Theory 方向21).

自然梯度: θ_{t+1} = θ_t - η F(θ)^{-1} ∇L(θ)
Fisher信息矩阵→参数化不变的黎曼度量→最陡下降.

用法:
    ig = InfoGeometry()
    ng = ig.natural_gradient(grad, fisher_diag)
"""
from __future__ import annotations
import math


class InfoGeometry:
    """信息几何——Fisher度规下的自然梯度."""

    @staticmethod
    def fisher_diag_approx(gradients: list[list[float]]) -> list[float]:
        """Fisher信息矩阵对角近似——∇log p(θ)的外积期望."""
        n = len(gradients)
        if n == 0:
            return []
        d = len(gradients[0])
        diag = [0.0] * d
        for g in gradients:
            for j in range(d):
                diag[j] += g[j] * g[j]
        return [v / n + 1e-6 for v in diag]  # +ε防除零

    @staticmethod
    def natural_gradient(grad: list[float],
                         fisher_diag: list[float],
                         lr: float = 0.01) -> list[float]:
        """自然梯度: θ_new = θ - η F^{-1} ∇L."""
        return [-lr * g / max(f, 1e-8) for g, f in zip(grad, fisher_diag)]

    @staticmethod
    def kl_divergence(p: list[float], q: list[float]) -> float:
        """KL散度 D_KL(p||q)——Fisher-Rao距离的局部近似."""
        d = 0.0
        for pi, qi in zip(p, q):
            if pi > 0 and qi > 0:
                d += pi * math.log(pi / qi)
        return d
