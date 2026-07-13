"""AnySearch 可选适配器 (V15.2).

当配置了 ANYSEARCH_API_KEY 且服务可用时，优先使用 AnySearch
作为搜索后端。不可用时自动跳过——不阻塞降级链。

环境变量:
    ANYSEARCH_API_KEY: AnySearch API Key（不设置则自动跳过）
"""

from __future__ import annotations

import os

import httpx
import structlog

from orbit.knowledge.search.sources.base import RawSearchItem, SearchSource

logger = structlog.get_logger("orbit.knowledge.search.sources.anysearch")

_ANYSEARCH_API = "https://api.anysearch.com/v1/search"


class AnySearchAdapter(SearchSource):
    """AnySearch 搜索适配器——可选加速源。"""

    name = "anysearch"
    priority = 10  # 最高优先——有 Key 时最优先使用

    def __init__(self) -> None:
        self._api_key = os.environ.get("ANYSEARCH_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            h = {"Content-Type": "application/json", "User-Agent": "Orbit-Agent/1.0"}
            if self._api_key:
                h["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), headers=h)
        return self._client

    async def search(self, query: str, max_results: int = 10) -> list[RawSearchItem]:
        if not self.is_configured:
            return []

        client = await self._get_client()
        try:
            resp = await client.post(
                _ANYSEARCH_API,
                json={"query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
            results = (data.get("data", {}).get("results", []) or [])[:max_results]

            items: list[RawSearchItem] = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                items.append(
                    RawSearchItem(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("description", "")[:500],
                        content_markdown=r.get("content", ""),
                        source_name="anysearch",
                    )
                )
            logger.debug("anysearch_done", query=query[:50], count=len(items))
            return items

        except Exception as e:
            logger.warning("anysearch_failed", error=str(e)[:100])
            return []

    async def health_check(self) -> bool:
        if not self.is_configured:
            return False
        try:
            client = await self._get_client()
            resp = await client.post(
                _ANYSEARCH_API, json={"query": "test", "max_results": 1}
            )
            return resp.status_code < 500 and "code" in resp.json()
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
