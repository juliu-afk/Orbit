"""拓扑数据分析 (V14.2+Theory 方向12).

持久同调——VR复形过滤序列→持久条形码→多尺度孔洞检测.
β₁非零区间=跨跳隐藏循环依赖.

用法:
    tda = TDAAnalyzer()
    barcode = tda.persistence_barcode(adj_matrix, max_dim=1)
"""
from __future__ import annotations


class TDAAnalyzer:
    """持久同调分析器——自实现,无需gudhi/ripser."""

    def persistence_barcode(self, adj_matrix,
                            max_dim: int = 1) -> dict[int, list[tuple[float, float]]]:
        """计算简化持久条形码(0维+1维).

        adj_matrix: 距离矩阵(非邻接——0=相同,∞=不连通)
        Returns: {dim: [(birth, death), ...]}
        """
        n = len(adj_matrix)
        if n < 3:
            return {0: [], 1: []}
        # 简化: Kruskal MST→0维条形码
        edges = []
        for i in range(n):
            for j in range(i + 1, n):
                if adj_matrix[i][j] < float("inf"):
                    edges.append((adj_matrix[i][j], i, j))
        edges.sort()
        parent = list(range(n))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx
                return True
            return False
        # 0维: 每个merge的edge weight=death, birth=0
        dim0 = [(0.0, e[0]) for e in edges if union(e[1], e[2])]
        # 1维: 简化——三角形闭合检测
        dim1 = self._detect_cycles(adj_matrix, edges)
        return {0: dim0, 1: dim1}

    @staticmethod
    def _detect_cycles(adj, edges) -> list[tuple[float, float]]:
        """检测1维孔洞(环)——简化持久同调."""
        cycles = []
        for w, i, j in edges:
            for k in range(len(adj)):
                if k != i and k != j:
                    if adj[i][k] < float("inf") and adj[k][j] < float("inf"):
                        birth = max(w, adj[i][k], adj[k][j])
                        if birth > 0:
                            cycles.append((birth, float("inf")))
                        break
        return cycles[:5]

    @staticmethod
    def betti_summary(barcode: dict) -> dict[int, int]:
        """持久Betti数——每维度非零条形码计数."""
        return {dim: sum(1 for b, d in bars if d > b or d == float("inf"))
                for dim, bars in barcode.items()}
