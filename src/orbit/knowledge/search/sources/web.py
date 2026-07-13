"""通用网页搜索——SearXNG 适配器 (V15.2).

开源、可自托管的元搜索引擎。支持 JSON API。
MVP 阶段默认用公共实例，生产环境通过环境变量指定自托管地址。

环境变量:
    SEARXNG_URL: SearXNG 实例地址（默认 https://searx.be）
"""

from __future__ import annotations

import os

import httpx
import structlog

from orbit.knowledge.search.sources.base import RawSearchItem, SearchSource

logger = structlog.get_logger("orbit.knowledge.search.sources.web")

_DEFAULT_SEARXNG_URL = "https://searx.be"


class WebSource(SearchSource):
    """SearXNG 通用网页搜索适配器。"""

    name = "web"
    priority = 20  # 第二优先——AnySearch 之后

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.environ.get("SEARXNG_URL", _DEFAULT_SEARXNG_URL)).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._client

    async def search(self, query: str, max_results: int = 10) -> list[RawSearchItem]:
        """调用 SearXNG JSON API。"""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self._base_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[:max_results]

            items: list[RawSearchItem] = []
            for r in results:
                items.append(
                    RawSearchItem(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("content", "")[:500],
                        source_name="searxng",
                    )
                )
            logger.debug("web_search_done", query=query[:50], count=len(items))
            return items

        except Exception as e:
            logger.warning("web_search_failed", error=str(e)[:100])
            return []

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self._base_url}/search", params={"q": "test", "format": "json"})
            return resp.status_code < 500
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
