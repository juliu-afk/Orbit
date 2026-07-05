"""上下文匹配引擎 + 预构建器 (Phase 2 Token节省).

- ContextMatcher: NL→关键词→项目匹配→候选排序 (已有)
- ContextPrebuilder: Agent dispatch 前按角色裁剪 context (新增)
- Scanners: 确定性预扫描器 (新增)
- Builders: 上下文包构建器 (新增)
"""

from orbit.context.matcher import ContextMatcher, MatchCandidate, MatchResult
from orbit.context.prebuilder import ContextPrebuilder

__all__ = [
    "ContextMatcher",
    "MatchCandidate",
    "MatchResult",
    "ContextPrebuilder",
]
