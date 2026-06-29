"""上下文相关性打分——基于 ast 模块精确到函数/类级别。

WHY: PromptBuilder._build_context() 当前硬截断 5000 字符。
     改为按任务关键词提取最相关的函数/类定义，降噪减熵。
     Python ast 是标准库，无需额外依赖。

用法:
    scorer = RelevanceScorer()
    fragments = scorer.score(source_code, ["calculate_tax", "税率"])
    # → [CodeFragment(identifier="calculate_tax", relevance=0.85, ...), ...]
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class CodeFragment:
    """提取出的代码片段——函数或类定义的一部分。"""

    identifier: str         # 函数名/类名
    node_type: str          # "function" / "async_function" / "class"
    source: str             # 完整源代码（含签名和 body）
    line_start: int
    line_end: int
    relevance_score: float  # 0.0-1.0，越高越相关


# ── 相关性打分权重 ────────────────────────────────────────────

# 标识符直接包含关键词的权重
EXACT_MATCH_WEIGHT = 0.6
# 标识符包含关键词子串的权重
SUBSTRING_MATCH_WEIGHT = 0.35
# 函数体内出现关键词的权重
BODY_MATCH_WEIGHT = 0.2
# 被调用函数名包含关键词的权重
CALLEE_MATCH_WEIGHT = 0.1


class RelevanceScorer:
    """基于 ast 的关键词->代码片段相关性打分器。

    策略:
    1. 解析源码为 AST
    2. 提取所有顶层函数/类定义（含源代码原文）
    3. 对每个定义按关键词计算权重
    4. 返回 Top-N 相关片段

    复杂度: O(n_definitions × n_keywords)，n_definitions 通常 < 50
    """

    def __init__(self) -> None:
        pass

    def score(
        self,
        source_code: str,
        keywords: list[str],
        max_fragments: int = 5,
    ) -> list[CodeFragment]:
        """对源码中的函数/类定义做相关性打分，返回 Top-N。

        Args:
            source_code: Python 源文件内容
            keywords: 任务关键词列表（已去停用词）
            max_fragments: 最多返回 N 个片段

        Returns:
            按 relevance_score 降序排列的片段列表。
            如果解析失败或没有匹配，返回空列表。
        """
        if not source_code.strip() or not keywords:
            return []

        keywords_lower = [k.lower() for k in keywords]

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            # 语法错误时降级——返回空，调用者应回退到全文截断
            return []

        lines = source_code.splitlines()
        fragments: list[CodeFragment] = []

        for node in ast.walk(tree):
            # 只处理顶层函数和类
            if not isinstance(
                node,
                ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
            ):
                continue

            fragment = self._extract_fragment(
                node, lines, keywords_lower
            )
            if fragment and fragment.relevance_score > 0:
                fragments.append(fragment)

        # 按相关性降序
        fragments.sort(key=lambda f: f.relevance_score, reverse=True)
        return fragments[:max_fragments]

    def _extract_fragment(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        lines: list[str],
        keywords_lower: list[str],
    ) -> CodeFragment | None:
        """提取单个定义节点并打分。"""
        identifier = node.name
        if not identifier:
            return None

        id_lower = identifier.lower()
        score = 0.0

        # ── 打分规则 ──

        # 1. 标识符精确包含关键词
        for kw in keywords_lower:
            if kw in id_lower:
                if id_lower == kw:
                    score += EXACT_MATCH_WEIGHT
                else:
                    score += SUBSTRING_MATCH_WEIGHT

        # 2. 源代码原文提取
        line_start = node.lineno
        line_end = node.end_lineno or line_start
        if 1 <= line_start <= len(lines) and 1 <= line_end <= len(lines):
            source = "\n".join(lines[line_start - 1 : line_end])
        else:
            source = ""

        # 3. 函数体内关键词命中（从源码字符串搜，避免 AST 嵌套遍历）
        if source:
            source_lower = source.lower()
            for kw in keywords_lower:
                if kw in source_lower:
                    score += BODY_MATCH_WEIGHT

        # 4. 被调用函数名包含关键词（从 AST 提取调用）
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee_name = self._get_call_name(child)
                if callee_name:
                    callee_lower = callee_name.lower()
                    for kw in keywords_lower:
                        if kw in callee_lower:
                            score += CALLEE_MATCH_WEIGHT
                            break

        # 归一化到 0-1
        max_possible = (
            len(keywords_lower)
            * (EXACT_MATCH_WEIGHT + BODY_MATCH_WEIGHT + CALLEE_MATCH_WEIGHT)
        )
        normalized = min(score / max(0.1, max_possible), 1.0)

        node_type = (
            "async_function"
            if isinstance(node, ast.AsyncFunctionDef)
            else "class"
            if isinstance(node, ast.ClassDef)
            else "function"
        )

        return CodeFragment(
            identifier=identifier,
            node_type=node_type,
            source=source,
            line_start=line_start,
            line_end=line_end,
            relevance_score=round(normalized, 3),
        )

    @staticmethod
    def _get_call_name(node: ast.Call) -> str | None:
        """从 ast.Call 节点提取被调用函数名。"""
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None


def extract_relevant_context(
    source_code: str,
    keywords: list[str],
    max_fragments: int = 5,
    max_chars: int = 5000,
) -> str:
    """便捷函数：提取相关代码片段并拼接。

    如果没有命中任何片段，返回全文截断。
    这是 prompt/builder.py _build_context() 的直接替代品。

    Args:
        source_code: Python 源文件内容
        keywords: 任务关键词
        max_fragments: 最多返回片段数
        max_chars: 最大字符数（超出截断）

    Returns:
        拼接后的相关代码文本
    """
    scorer = RelevanceScorer()
    fragments = scorer.score(source_code, keywords, max_fragments)

    if not fragments:
        # 降级：无命中 → 全文截断
        if len(source_code) > max_chars:
            return source_code[:max_chars] + "\n... (截断)"
        return source_code

    parts: list[str] = [
        f"# {f.node_type} {f.identifier} (相关度={f.relevance_score:.2f})"
        f"\n{f.source}"
        for f in fragments
    ]
    result = "\n\n".join(parts)

    # 仍然做长度截断兜底
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... (截断)"

    return result
