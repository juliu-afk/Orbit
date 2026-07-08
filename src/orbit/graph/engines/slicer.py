"""程序切片 (V14.2+Theory 方向24).

AST→CFG→DDG→PDG→图可达性查询:
  前向切片: 第N行变量影响哪些输出行
  后向切片: 输出X依赖哪些行

用法:
    from orbit.graph.engines.slicer import ProgramSlicer
    slicer = ProgramSlicer()
    lines = slicer.forward_slice(code, line=42, var="result")
"""
from __future__ import annotations
import ast


class ProgramSlicer:
    """基于AST的程序切片——前向/后向数据依赖分析."""

    def forward_slice(self, code: str, line: int, var: str) -> set[int]:
        """从line行var变量出发——影响哪些行的输出."""
        tree = self._parse(code)
        if tree is None:
            return set()
        # 构建简化PDG: {line: {defs, uses}}
        pdg = self._build_pdg(tree)
        target = None
        for ln, info in pdg.items():
            if ln == line and var in info.get("defs", set()):
                target = ln
                break
        if target is None:
            return set()
        # BFS从target出发——沿数据依赖边传播
        return self._reachable(pdg, target)

    def backward_slice(self, code: str, line: int) -> set[int]:
        """line行输出依赖哪些行."""
        tree = self._parse(code)
        if tree is None:
            return set()
        pdg = self._build_pdg(tree)
        # 找line行使用的变量→反向追踪定义这些变量的行
        uses = pdg.get(line, {}).get("uses", set())
        if not uses:
            return set()
        result: set[int] = set()
        for var in uses:
            for ln, info in pdg.items():
                if var in info.get("defs", set()):
                    result.add(ln)
                    # 递归反向追踪
                    result |= self.backward_slice(code, ln)
        return result

    # ── 内部 ──────────────────────────────────────────

    def _parse(self, code: str):
        try:
            return ast.parse(code)
        except SyntaxError:
            return None

    @staticmethod
    def _build_pdg(tree: ast.AST) -> dict[int, dict]:
        """构建简化程序依赖图: {line_number: {defs:set, uses:set}}."""
        pdg: dict[int, dict] = {}
        for node in ast.walk(tree):
            ln = getattr(node, 'lineno', 0)
            if ln == 0:
                continue
            if ln not in pdg:
                pdg[ln] = {"defs": set(), "uses": set()}
            # 赋值→def
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    for name_node in ast.walk(target):
                        if isinstance(name_node, ast.Name):
                            pdg[ln]["defs"].add(name_node.id)
            # Name加载→use
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                pdg[ln]["uses"].add(node.id)
        return pdg

    @staticmethod
    def _reachable(pdg: dict, start: int) -> set[int]:
        """从start出发可达的行."""
        visited = {start}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            defs = pdg.get(cur, {}).get("defs", set())
            for ln, info in pdg.items():
                if ln in visited:
                    continue
                if defs & info.get("uses", set()):
                    visited.add(ln)
                    queue.append(ln)
        return visited - {start}
