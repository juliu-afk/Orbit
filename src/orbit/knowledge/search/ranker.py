"""搜索结果排序 (V15.2).

三道工序——去重 → 同源衰减 → 信息密度仲裁。
纯 Python 实现，零新依赖。

参考: AnySearch 同源衰减算法 + 信息密度仲裁算法。
"""

from __future__ import annotations

from orbit.knowledge.search.sources.base import RawSearchItem, SearchResult


class Ranker:
    """搜索结果排序器——去重 + 衰减 + 仲裁。

    Usage:
        ranker = Ranker()
        results = ranker.rank(items, query="...")
    """

    # 同源衰减参数
    SAME_SOURCE_DECAY = 0.7   # 同域名第 N 条结果的权重衰减因子
    MAX_SAME_SOURCE = 3        # 同一域名最多保留条数

    def rank(
        self, items: list[RawSearchItem], query: str = ""
    ) -> list[SearchResult]:
        """完整排序管线——去重→衰减→仲裁→转换。"""
        if not items:
            return []

        items = self._dedup_by_url(items)
        items = self._same_source_attenuation(items)
        items = self._info_density_arbitration(items)

        # 转换 RawSearchItem → SearchResult
        results: list[SearchResult] = []
        for item in items:
            results.append(
                SearchResult(
                    title=item.title,
                    url=item.url,
                    snippet=item.snippet,
                    content=item.content_markdown or item.snippet,
                    source_name=item.source_name,
                    relevance_score=item.relevance_score,
                )
            )

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results

    def _dedup_by_url(self, items: list[RawSearchItem]) -> list[RawSearchItem]:
        """按 URL 去重——保留第一次出现的条目。"""
        seen: set[str] = set()
        unique: list[RawSearchItem] = []
        for item in items:
            normalized = item.url.rstrip("/").lower()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(item)
        return unique

    def _same_source_attenuation(
        self, items: list[RawSearchItem]
    ) -> list[RawSearchItem]:
        """同源衰减——同一域名多条结果时降权。

        WHY: 搜索引擎经常让同一网站占据多个结果位。
        对人来说多翻几页即可，对 Agent 来说会稀释有效信息、浪费 Token。
        """
        from urllib.parse import urlparse

        domain_counts: dict[str, int] = {}
        for item in items:
            try:
                domain = urlparse(item.url).netloc
            except Exception:
                domain = item.url
            count = domain_counts.get(domain, 0) + 1
            domain_counts[domain] = count

            if count > self.MAX_SAME_SOURCE:
                # 超过上限→大幅降权，排在末尾
                item.relevance_score *= 0.1
            elif count > 1:
                # 同域第 2-3 条→按衰减因子降权
                item.relevance_score *= self.SAME_SOURCE_DECAY

        return items

    def _info_density_arbitration(
        self, items: list[RawSearchItem]
    ) -> list[RawSearchItem]:
        """信息密度仲裁——内容更丰富的条目提权。

        WHY: 两个条目相关性相近时，优先保留信息量更丰富的。
        评分依据: snippet 长度 + content 长度 + URL 路径深度。
        """
        for item in items:
            density_score = 0.0

            # snippet 长度——超过 100 字符的是有效摘要
            if len(item.snippet) > 100:
                density_score += 0.15
            if len(item.snippet) > 300:
                density_score += 0.1

            # content（Markdown 正文）存在且非空→高密度信号
            if item.content_markdown and len(item.content_markdown) > 200:
                density_score += 0.25

            # URL 路径深度——路径越深通常内容越具体
            from urllib.parse import urlparse
            try:
                path_segments = [s for s in urlparse(item.url).path.split("/") if s]
                if len(path_segments) >= 3:
                    density_score += 0.05
            except Exception:
                pass

            item.relevance_score += density_score

        return items
