"""拓扑数据分析 (V14.2+Theory 方向12). P1修复: 环空间检测替代三角形."""
from __future__ import annotations

class TDAAnalyzer:
    def persistence_barcode(self, adj_matrix, max_dim: int = 1):
        """简化持久条形码——0维Kruskal + 1维环空间."""
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
        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry: parent[ry] = rx; return True
            return False
        # 0维: MST merge
        dim0 = [(0.0, e[0]) for e in edges if union(e[1], e[2])]
        # 1维: 不在MST中的边产生环(未被填充)
        dim1 = []
        for w, i, j in edges:
            if find(i) == find(j):
                dim1.append((w, float("inf")))
        return {0: dim0, 1: dim1}

    @staticmethod
    def betti_summary(barcode):
        return {dim: sum(1 for b, d in bars if d > b or d == float("inf"))
                for dim, bars in barcode.items()}
