"""图谱频谱分析 (V14.2+Theory 方向3).

对代码图邻接矩阵做拉普拉斯特征分解:
  λ₂ = Fiedler值（代数连通性）
  v₂ = Fiedler向量（自然二分——min-cut的连续松弛）
  ρ(A) = 谱半径（变更传播最坏范围）

用法:
    from orbit.graph.spectral import SpectralAnalyzer
    sa = SpectralAnalyzer()
    report = sa.analyze(code_graph.adjacency_matrix())
    print(report.fiedler_gap, report.modularity)
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

try:
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass
class SpectralReport:
    algebraic_connectivity: float = 0.0  # λ₂——越高模块耦合越紧
    fiedler_gap: float = 0.0             # λ₃−λ₂——间隙越大分割越自然
    spectral_radius: float = 0.0         # ρ——最坏变更传播范围
    partition: np.ndarray | None = None  # Fiedler向量符号→二分
    modularity: float = 0.0              # 模块化评分


class SpectralAnalyzer:
    """图拉普拉斯频谱分析器."""

    def analyze(self, adj_matrix) -> SpectralReport:
        """输入邻接矩阵(sparse CSC)→频谱报告."""
        if not HAS_SCIPY:
            return SpectralReport()
        n = adj_matrix.shape[0]
        if n < 3:
            return SpectralReport()
        # L = D - A
        degrees = np.array(adj_matrix.sum(axis=1)).flatten()
        L = sp.spdiags(degrees, 0, n, n) - adj_matrix
        try:
            evals, evecs = spla.eigsh(L.astype(float), k=min(5, n-1), which='SM')
        except Exception:
            return SpectralReport()
        fiedler_vec = evecs[:, 1] if evecs.shape[1] > 1 else evecs[:, 0]
        partition = np.where(fiedler_vec >= 0, 1, 0)
        # 谱半径
        try:
            d_inv = np.where(degrees > 0, 1.0 / np.sqrt(degrees), 0.0)
            D_sqrt_inv = sp.spdiags(d_inv, 0, n, n)
            L_norm = sp.eye(n) - D_sqrt_inv @ adj_matrix @ D_sqrt_inv
            sr = spla.eigsh(L_norm.astype(float), k=1, which='LM', return_eigenvectors=False)[0]
        except Exception:
            sr = 0.0
        return SpectralReport(
            algebraic_connectivity=float(evals[1]) if len(evals) > 1 else 0.0,
            fiedler_gap=float(evals[2] - evals[1]) if len(evals) > 2 else 0.0,
            spectral_radius=float(sr),
            partition=partition,
            modularity=self._modularity(adj_matrix, partition),
        )

    def _modularity(self, adj, partition) -> float:
        """Newman-Girvan modularity."""
        m = adj.sum() / 2.0
        if m == 0:
            return 0.0
        degrees = np.array(adj.sum(axis=1)).flatten()
        Q = 0.0
        for i in range(adj.shape[0]):
            for j in range(adj.shape[0]):
                if partition[i] == partition[j] and i != j:
                    Q += adj[i, j] - degrees[i] * degrees[j] / (2.0 * m)
        return float(Q / (2.0 * m))
