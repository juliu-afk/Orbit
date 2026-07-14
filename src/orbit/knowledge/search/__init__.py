"""Agent 外部搜索模块 (V15.2).

为 Orbit Agent 提供实时外部信息检索能力。
架构: 意图路由 → 多源并行查询 → 前置筛选 → 结构化输出。
降级链: AnySearch → SearXNG → GitHub API → 本地 knowledge 回退。

Usage:
    from orbit.knowledge.search import search
    results = await search("Python async best practices", max_results=10)
"""

from __future__ import annotations

import asyncio

import structlog

from .intent_router import IntentRouter
from .ranker import Ranker
from .cache import SearchCache
from .extractor import ContentExtractor
from .sources.web import WebSource
from .sources.code import CodeSource
from .sources.anysearch import AnySearchAdapter

logger = structlog.get_logger("orbit.knowledge.search")

# 全局单例——懒初始化
_cache: SearchCache | None = None
_ranker = Ranker()
_extractor = ContentExtractor()


def _get_cache() -> SearchCache:
    global _cache
    if _cache is None:
        _cache = SearchCache("data/search_cache.db")
    return _cache


async def search(
    query: str,
    max_results: int = 10,
    llm_client: object = None,
) -> list[dict]:
    """Agent 外部搜索主入口——串联意图路由→多源查询→排序→缓存。

    降级顺序: AnySearch → WebSource(SearXNG) → CodeSource(GitHub) → []
    每源独立超时 3s，连续失败 3 次自动跳过 5min。

    Args:
        query: 搜索查询
        max_results: 最大返回条数
        llm_client: LLM 客户端——用于意图路由（None 时全源搜索）

    Returns:
        [{"title": str, "url": str, "snippet": str, "content": str, "source": str}, ...]
    """
    if not query.strip():
        return []

    # 1. 缓存命中
    cache = _get_cache()
    cached = cache.get(query)
    if cached:
        logger.debug("search_cache_hit", query=query[:50])
        return cached[:max_results]

    # 2. 意图路由——选择数据源
    router = IntentRouter(llm_client)
    intent = await router.route(query)
    source_names = router.sources_for(intent)
    logger.debug("search_intent", query=query[:50], intent=intent, sources=source_names)

    # 3. 组装数据源——按优先级排序
    sources: list = []
    if "anysearch" in source_names:
        sources.append(AnySearchAdapter())
    if "web" in source_names:
        sources.append(WebSource())
    if "code" in source_names:
        sources.append(CodeSource())
    sources.sort(key=lambda s: s.priority)

    # 4. 并行查询所有源
    all_items = []
    async with asyncio.TaskGroup() as tg:
        tasks = {}
        for src in sources:
            tasks[src.name] = tg.create_task(
                _safe_search(src, query, max_results)
            )

    # 5. 合并+排序
    for src_name, task in tasks.items():
        try:
            items = task.result()
            all_items.extend(items)
        except Exception as e:
            logger.warning("search_source_failed", source=src_name, error=str(e)[:80])

    if not all_items:
        return []

    results = _ranker.rank(all_items, query)

    # 6. 写入缓存
    cache.set(query, [_result_to_dict(r) for r in results])

    return [_result_to_dict(r) for r in results[:max_results]]


async def _safe_search(source, query, max_results):
    """安全搜索——独立超时+异常捕获，不阻塞其他源。"""
    try:
        return await asyncio.wait_for(
            source.search(query, max_results), timeout=3.0
        )
    except asyncio.TimeoutError:
        logger.warning("search_source_timeout", source=source.name)
        return []
    except Exception as e:
        logger.warning("search_source_error", source=source.name, error=str(e)[:80])
        return []


def _result_to_dict(r) -> dict:
    from .sources.base import SearchResult
    if isinstance(r, SearchResult):
        return {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "content": r.content,
            "source": r.source_name,
        }
    return {"title": str(r), "url": "", "snippet": "", "content": "", "source": "unknown"}


__all__ = [
    "IntentRouter",
    "Ranker",
    "SearchCache",
    "ContentExtractor",
    "search",
]
