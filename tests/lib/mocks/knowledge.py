"""Mock 知识库——替代 knowledge/store.py:KnowledgeStore。

可配置查询结果、命中率、延迟。纯内存，无 SQLite 依赖。
"""

from __future__ import annotations

import random
from typing import Any


class MockKnowledgeStore:
    """Mock 知识库——替代 knowledge/store.py:KnowledgeStore。100% 兼容 query_exact/query 接口。"""

    def __init__(
        self,
        query_results: list[dict[str, Any]] | None = None,
        hit_rate: float = 1.0,
        latency_ms: int = 10,
    ) -> None:
        self._results: dict[str, dict[str, Any]] = {}
        if query_results:
            for r in query_results:
                key = f"{r.get('domain', '')}:{r.get('concept', '')}"
                self._results[key] = r
        self.hit_rate = hit_rate
        self.latency_ms = latency_ms
        self.query_count: int = 0
        self.queries: list[tuple[str, str]] = []

    def with_results(self, results: list[dict[str, Any]]) -> "MockKnowledgeStore":
        self._results.clear()
        for r in results:
            key = f"{r.get('domain', '')}:{r.get('concept', '')}"
            self._results[key] = r
        return self

    def with_hit_rate(self, rate: float) -> "MockKnowledgeStore":
        self.hit_rate = max(0.0, min(1.0, rate))
        return self

    async def query(self, domain: str, concept: str) -> list[dict[str, Any]]:
        self.query_count += 1
        self.queries.append((domain, concept))
        if self.hit_rate < 1.0 and random.random() > self.hit_rate:
            return []
        key = f"{domain}:{concept}"
        result = self._results.get(key)
        return [result] if result is not None else []

    def query_exact(self, domain: str, concept: str) -> dict[str, Any] | None:
        self.query_count += 1
        self.queries.append((domain, concept))
        if self.hit_rate < 1.0 and random.random() > self.hit_rate:
            return None
        key = f"{domain}:{concept}"
        return self._results.get(key)

    def initialize(self) -> None:
        pass

    def reset(self) -> None:
        self.query_count = 0
        self.queries.clear()
