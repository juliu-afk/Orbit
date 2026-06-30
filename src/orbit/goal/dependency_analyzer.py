"""DependencyAnalyzer——复数任务依赖关联分析。

三层检测:
1. 显式声明: frontmatter depends_on, @depends-on 注释
2. 文件冲突: CodeGraph 预测两个 Goal 涉及的文件集 → 交集=冲突
3. 隐式推断: 廉价 LLM (temperature=0) 语义分析 → 建议依赖边

输出: 拓扑分层 DAG——同层可并行，层间串行。

WHY 三层: 显式最可靠，文件冲突最安全，隐式作为补充——
三层合并确保不会排错执行顺序。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from orbit.goal.models import DepEdge, DependencyConflict

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient
    from orbit.goal.models import GoalSession
    from orbit.graph.engines.code_graph import CodeGraphEngine

logger = structlog.get_logger("orbit.goal")


class DependencyAnalyzer:
    """复数任务依赖分析器。

    Usage:
        analyzer = DependencyAnalyzer(codegraph=..., cheap_llm=...)
        dag = await analyzer.analyze(goals, codebase_root=".")
        # dag.layers[0] = 可并行的 Goal 列表
        # dag.layers[1] = 依赖 layer 0 的 Goal 列表
    """

    def __init__(
        self,
        codegraph: Any = None,  # CodeGraphEngine
        cheap_llm: Any = None,  # LLMClient (廉价模型，仅隐式推断用)
    ) -> None:
        self._codegraph = codegraph
        self._cheap_llm = cheap_llm

    async def analyze(
        self,
        goals: list[GoalSession],
        codebase_root: str = ".",
    ) -> dict:
        """分析复数 Goal 之间的依赖关系，输出拓扑分层 DAG。

        Returns:
            {
                "layers": [[GoalSession, ...], ...],
                "edges": [DepEdge, ...],
                "conflicts": [DependencyConflict, ...]
            }
        """
        if len(goals) <= 1:
            return {"layers": [goals], "edges": [], "conflicts": []}

        # 1. 显式声明——从文档内容提取
        explicit_deps = self._extract_explicit_deps(goals)

        # 2. 文件冲突——CodeGraph 搜索
        file_conflicts = await self._detect_file_conflicts(goals, codebase_root)

        # 3. 隐式推断——LLM 轻量语义分析
        implicit_deps = await self._infer_implicit_deps(goals)

        # 4. 合并依赖边 + 拓扑分层
        all_edges = explicit_deps + file_conflicts + implicit_deps
        layers = self._topological_layers(goals, all_edges)

        # 5. 检测冲突
        conflicts = self._detect_conflicts(layers, all_edges)

        logger.info(
            "dependency_analysis_complete",
            total_goals=len(goals),
            layers=len(layers),
            explicit=len(explicit_deps),
            file_conflicts=len(file_conflicts),
            implicit=len(implicit_deps),
            conflicts=len(conflicts),
        )
        return {
            "layers": layers,
            "edges": [e.model_dump() for e in all_edges],
            "conflicts": [c.model_dump() for c in conflicts],
        }

    # ── 内部: 显式依赖 ─────────────────────────────────

    def _extract_explicit_deps(self, goals: list[GoalSession]) -> list[DepEdge]:
        """从文档内容提取显式依赖。

        来源:
        - YAML frontmatter: depends_on: ["认证模块"]
        - 文档内 @depends-on 注释
        - 前文档声明 "前置 PRD"
        """
        edges: list[DepEdge] = []
        for goal in goals:
            desc = goal.description

            # 方法1: frontmatter depends_on
            if "depends_on" in desc or "depends-on" in desc.lower():
                # 简化的启发式提取——找引号中的依赖名
                import re

                deps = re.findall(r"depends_on:\s*\[(.*?)\]", desc, re.IGNORECASE)
                if not deps:
                    deps = re.findall(r"depends[_\\-]on:\s*\[(.*?)\]", desc, re.IGNORECASE)
                for dep_group in deps:
                    # 解析 JSON 数组
                    try:
                        dep_names = json.loads(
                            dep_group if dep_group.startswith("[") else f"[{dep_group}]"
                        )
                    except json.JSONDecodeError:
                        # 非 JSON——逗号分隔
                        dep_names = [d.strip().strip("\"'") for d in dep_group.split(",")]
                    for dep_name in dep_names:
                        dep_goal = self._find_goal_by_name(goals, dep_name)
                        if dep_goal and dep_goal.id != goal.id:
                            edges.append(
                                DepEdge(
                                    from_id=dep_goal.id,
                                    to_id=goal.id,
                                    type="explicit",
                                    source=f"frontmatter: depends_on={dep_name}",
                                )
                            )

            # 方法2: "@depends-on" 注释
            if "@depends-on" in desc.lower():
                import re

                refs = re.findall(r"@depends-on\s+(\S+)", desc, re.IGNORECASE)
                for ref in refs:
                    dep_goal = self._find_goal_by_name(goals, ref)
                    if dep_goal and dep_goal.id != goal.id:
                        edges.append(
                            DepEdge(
                                from_id=dep_goal.id,
                                to_id=goal.id,
                                type="explicit",
                                source=f"@depends-on {ref}",
                            )
                        )

        return edges

    # ── 内部: 文件冲突 ─────────────────────────────────

    async def _detect_file_conflicts(
        self,
        goals: list[GoalSession],
        codebase_root: str,
    ) -> list[DepEdge]:
        """检测文件冲突——两个 Goal 可能修改同一文件。

        方法: 对每个 Goal 提取关键词 → CodeGraph 搜索 → 预测涉及文件。
        交集 → 冲突边（串行执行，避免 merge conflict）。
        """
        if not self._codegraph:
            return []

        # 提取关键词 + 预测文件
        goal_files: dict[str, set[str]] = {}
        for goal in goals:
            keywords = self._extract_keywords(goal.description)
            if not keywords:
                goal_files[goal.id] = set()
                continue
            try:
                files = await self._codegraph.search_files(keywords, top_k=10)
                goal_files[goal.id] = set(files)
            except Exception as e:
                logger.warning("codegraph_search_failed", goal_id=goal.id, error=str(e))
                goal_files[goal.id] = set()

        # 检测交集
        edges: list[DepEdge] = []
        goal_list = list(goals)
        for i in range(len(goal_list)):
            for j in range(i + 1, len(goal_list)):
                a, b = goal_list[i], goal_list[j]
                overlap = goal_files[a.id] & goal_files[b.id]
                if overlap:
                    overlap_str = ", ".join(sorted(overlap)[:5])
                    edges.append(
                        DepEdge(
                            from_id=a.id,  # 先登记的/a 先执行
                            to_id=b.id,
                            type="file_conflict",
                            source=f"共享文件: {overlap_str}",
                        )
                    )

        return edges

    # ── 内部: 隐式推断 ─────────────────────────────────

    async def _infer_implicit_deps(
        self,
        goals: list[GoalSession],
    ) -> list[DepEdge]:
        """LLM 轻量语义推断——检测文档间未声明的依赖。

        示例:
        - "前端登录表单" 需要 "POST /auth/login API"
        - "报表导出测试" 需要 "报表导出功能"

        用廉价模型（temperature=0），不强制——标记为 implicit。
        """
        if len(goals) <= 1 or not self._cheap_llm:
            return []

        # 构建检测 prompt
        desc_list = "\n---\n".join(f"PRD {i+1}: {g.description[:200]}" for i, g in enumerate(goals))
        prompt = (
            "检测以下 PRD 之间是否存在未声明的依赖关系。"
            "只输出确实存在的依赖——不确定就不要输出。\n\n"
            f"{desc_list}\n\n"
            '输出 JSON: [{"from": N, "to": M, "reason": "..."}]'
            "其中 N 和 M 是 PRD 序号（1-based）。"
        )

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=prompt,
                system_prompt="你是依赖分析助手。只检测确定存在的依赖，不猜测。",
                temperature=0.0,
                max_tokens=300,
            )
            response = await self._cheap_llm.generate(req, task_id="dep_infer")
            return self._parse_implicit_response(response.content or "", goals)
        except Exception as e:
            logger.warning("implicit_dep_inference_failed", error=str(e))
            return []

    def _parse_implicit_response(
        self,
        content: str,
        goals: list[GoalSession],
    ) -> list[DepEdge]:
        """解析隐式推断 LLM 响应。"""
        try:
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.strip("`")
                if clean.startswith("json"):
                    clean = clean[4:]
            data = json.loads(clean)
        except (json.JSONDecodeError, TypeError):
            return []

        edges: list[DepEdge] = []
        for dep in data if isinstance(data, list) else []:
            try:
                from_idx = int(dep.get("from", 0)) - 1
                to_idx = int(dep.get("to", 0)) - 1
                if 0 <= from_idx < len(goals) and 0 <= to_idx < len(goals):
                    edges.append(
                        DepEdge(
                            from_id=goals[from_idx].id,
                            to_id=goals[to_idx].id,
                            type="implicit",
                            source=dep.get("reason", ""),
                            confidence=0.6,  # 隐式推断置信度低于显式
                        )
                    )
            except (ValueError, IndexError):
                continue
        return edges

    # ── 内部: 拓扑分层 ─────────────────────────────────

    def _topological_layers(
        self,
        goals: list[GoalSession],
        edges: list[DepEdge],
    ) -> list[list[GoalSession]]:
        """Kahn 算法变体——按层分组。

        同层无依赖关系 → 可并行执行。
        """
        goal_map = {g.id: g for g in goals}
        in_degree: dict[str, int] = {g.id: 0 for g in goals}
        adj: dict[str, list[str]] = {g.id: [] for g in goals}

        for edge in edges:
            if edge.from_id in adj and edge.to_id in in_degree:
                adj[edge.from_id].append(edge.to_id)
                in_degree[edge.to_id] += 1

        layers: list[list[GoalSession]] = []
        current_layer = [g for g in goals if in_degree[g.id] == 0]

        while current_layer:
            layers.append(current_layer)
            next_layer: list[GoalSession] = []
            for g in current_layer:
                for neighbor in adj.get(g.id, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_layer.append(goal_map[neighbor])
            current_layer = next_layer

        return layers

    # ── 内部: 冲突检测 ─────────────────────────────────

    def _detect_conflicts(
        self,
        layers: list[list[GoalSession]],
        edges: list[DepEdge],
    ) -> list[DependencyConflict]:
        """检测环形依赖、自依赖。"""
        conflicts: list[DependencyConflict] = []

        # 环形依赖检测
        cycles = self._find_cycles(edges)
        for cycle in cycles:
            conflicts.append(
                DependencyConflict(
                    type="cycle",
                    goals=cycle,
                    suggestion="请拆分或合并这些 PRD 中涉及循环的部分",
                )
            )

        # 自依赖检测
        for edge in edges:
            if edge.from_id == edge.to_id:
                conflicts.append(
                    DependencyConflict(
                        type="self_ref",
                        goals=[edge.from_id],
                        suggestion="PRD 不应依赖自身",
                    )
                )

        return conflicts

    @staticmethod
    def _find_cycles(edges: list[DepEdge]) -> list[list[str]]:
        """检测有向图中的环——DFS。"""
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e.from_id, []).append(e.to_id)

        cycles: list[list[str]] = []
        visited: set[str] = set()
        stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            stack.add(node)
            path.append(node)
            for neighbor in adj.get(node, []):
                if neighbor in stack:
                    # 找到环
                    cycle_start = path.index(neighbor)
                    cycles.append(list(path[cycle_start:]))
                elif neighbor not in visited:
                    dfs(neighbor)
            path.pop()
            stack.discard(node)

        all_nodes = set(adj.keys()) | {e.to_id for e in edges}
        for node in all_nodes:
            if node not in visited:
                dfs(node)

        return cycles

    # ── 辅助 ──────────────────────────────────────────

    @staticmethod
    def _find_goal_by_name(goals: list[GoalSession], name: str) -> GoalSession | None:
        """按名称/ID 匹配 Goal。P0-3: word-boundary 避免子串误判。"""
        import re

        name_lower = name.strip().lower()
        for g in goals:
            if g.id.lower() == name_lower or g.description.strip().lower() == name_lower:
                return g
        try:
            pattern = re.compile(r"\b" + re.escape(name_lower) + r"\b", re.IGNORECASE)
        except re.error:
            return None
        best, best_len = None, float("inf")
        for g in goals:
            if pattern.search(g.description) and len(g.description) < best_len:
                best, best_len = g, len(g.description)
        return best

    @staticmethod
    def _extract_keywords(description: str) -> list[str]:
        """从描述中提取关键搜索词。"""
        # 简单分词——提取可能涉及的技术名词
        keywords = []
        # 驼峰/蛇形识别
        import re

        # 提取英文技术名词
        tech_words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", description)
        keywords.extend(tech_words[:5])
        # 提取中文技术名词（简化——取 2-4 字词）
        chinese_words = re.findall(r"[一-鿿]{2,4}", description)
        keywords.extend(chinese_words[:5])
        return keywords[:8]
