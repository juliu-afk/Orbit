"""Agent 外部搜索模块 (V15.2).

为 Orbit Agent 提供实时外部信息检索能力。
架构: 意图路由 → 多源并行查询 → 前置筛选 → 结构化输出。
降级链: AnySearch → SearXNG → GitHub API → 本地 knowledge 回退。

Usage:
    from orbit.knowledge.search import search
    results = await search("Python async best practices", max_results=10)
"""

from __future__ import annotations

from .intent_router import IntentRouter
from .ranker import Ranker
from .cache import SearchCache
from .extractor import ContentExtractor

__all__ = [
    "IntentRouter",
    "Ranker",
    "SearchCache",
    "ContentExtractor",
]
