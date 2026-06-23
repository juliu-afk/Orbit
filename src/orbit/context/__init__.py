"""NL交互 PR #2——上下文匹配引擎。

自然语言→关键词提取→项目匹配→候选排序。
"""

from orbit.context.matcher import ContextMatcher, MatchCandidate, MatchResult

__all__ = ["ContextMatcher", "MatchCandidate", "MatchResult"]
