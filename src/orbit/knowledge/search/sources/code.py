"""代码搜索——GitHub Search API 适配器 (V15.2).

搜索公开仓库的代码、Issue、PR 等。
MVP 阶段用未认证 API（60 次/小时限制），后续可加 token 提升限额。

环境变量:
    GITHUB_TOKEN: GitHub Personal Access Token（可选，提升 API 限额）
"""

from __future__ import annotations

import os

import httpx
import structlog

from orbit.knowledge.search.sources.base import RawSearchItem, SearchSource

logger = structlog.get_logger("orbit.knowledge.search.sources.code")

_GITHUB_API = "https://api.github.com"


class CodeSource(SearchSource):
    """GitHub 代码搜索适配器——搜索公开仓库。"""

    name = "code"
    priority = 30  # 第三优先

    def __init__(self) -> None:
        token = os.environ.get("GITHUB_TOKEN", "")
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Orbit-Agent/1.0",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0), headers=self._headers
            )
        return self._client

    async def search(self, query: str, max_results: int = 10) -> list[RawSearchItem]:
        """搜索 GitHub 代码——用 /search/code 查源码文件内容。"""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{_GITHUB_API}/search/code",
                params={"q": query, "per_page": min(max_results, 10)},
            )
            resp.raise_for_status()
            data = resp.json()
            items_raw = data.get("items", [])

            items: list[RawSearchItem] = []
            for r in items_raw:
                repo_name = r.get("repository", {}).get("full_name", "")
                path = r.get("path", "")
                items.append(
                    RawSearchItem(
                        title=f"{repo_name}/{path}",
                        url=r.get("html_url", ""),
                        snippet=f"GitHub 代码匹配: {path}",
                        source_name="github_code",
                        relevance_score=r.get("score", 0.0),
                    )
                )
            logger.debug("code_search_done", query=query[:50], count=len(items))
            return items

        except Exception as e:
            logger.warning("code_search_failed", error=str(e)[:100])
            return []

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{_GITHUB_API}/search/repositories", params={"q": "test", "per_page": 1})
            return resp.status_code < 500
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
