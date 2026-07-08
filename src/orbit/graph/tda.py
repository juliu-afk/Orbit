"""拓扑数据分析 (V14.2+Theory 方向12). P1修复: MST构建时同步检测环."""
from __future__ import annotations

class TDAAnalyzer:
    def persistence_barcode(self, adj_matrix, max_dim: int = 1):
        n = len(adj_matrix)
        if n < 3:
            return {0: [], 1: []}
        edges = []
        for i in range(n):
            for j in range(i + 1, n):
                w = adj_matrix[i][j] if isinstance(adj_matrix[i], list) else abs(i - j)
                if w < float("inf"):
                    edges.append((w, i, j))
        edges.sort()
        parent = list(range(n))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        dim0, dim1 = [], []
        for w, i, j in edges:
            ri, rj = find(i), find(j)
            if ri == rj:
                dim1.append((w, float("inf")))
            else:
                parent[rj] = ri
                dim0.append((0.0, w))
        # P2-6: 每个连通分量一个存活棒——Union-Find根节点数
        roots = len({find(i) for i in range(n)})
        dim0.extend([(0.0, float("inf"))] * roots)
        return {0: dim0, 1: dim1}

    @staticmethod
    def betti_summary(barcode):
        """P2-6修复: β₀只计存活组件(d==inf), β₁不变."""
        return {dim: sum(1 for b, d in bars if d == float("inf"))
                for dim, bars in barcode.items()}
