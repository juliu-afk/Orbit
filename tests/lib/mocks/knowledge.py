"""Mock 知识库——替代 knowledge/store.py:KnowledgeStore。

可配置查询结果、命中率、延迟。
用于测试中替代 SQLite 知识库查询。

使用示例:
    # 命中
    mock = MockKnowledgeStore(query_results=[{"concept": "CurrentRatio", ...}])
    # 未命中
    mock = MockKnowledgeStore(hit_rate=0.0)
"""

from __future__ import annotations

import random
from typing import Any


class MockKnowledgeStore:
    """Mock 知识库——替代 knowledge/store.py:KnowledgeStore。

    100% 兼容 query_exact()/query() 接口签名。纯内存，无 SQLite 依赖。
    """

    def __init__(
        self,
        query_results: list[dict[str, Any]] | None = None,
        hit_rate: float = 1.0,
        latency_ms: int = 10,
    ) -> None:
        """初始化 Mock 知识库。

        Args:
            query_results: 预设查询结果列表
            hit_rate: 命中率（1.0=全命中，0.0=全未命中）
            latency_ms: 模拟延迟（毫秒）
        """
        self._results: dict[str, dict[str, Any]] = {}

        # 按 (domain, concept) 键索引预设结果
        if query_results:
            for r in query_results:
                key = f"{r.get('domain', '')}:{r.get('concept', '')}"
                self._results[key] = r

        self.hit_rate = hit_rate
        self.latency_ms = latency_ms

        # 调用追踪
        self.query_count: int = 0
        self.queries: list[tuple[str, str]] = []  # (domain, concept) 列表

    # ── 链式配置方法 ──────────────────────────────────────

    def with_results(self, results: list[dict[str, Any]]) -> "MockKnowledgeStore":
        """设置预设查询结果。"""
        self._results.clear()
        for r in results:
            key = f"{r.get('domain', '')}:{r.get('concept', '')}"
            self._results[key] = r
        return self

    def with_hit_rate(self, rate: float) -> "MockKnowledgeStore":
        """设置命中率。"""
        self.hit_rate = max(0.0, min(1.0, rate))
        return self

    # ── 生产接口兼容方法 ──────────────────────────────────

    async def query(self, domain: str, concept: str) -> list[dict[str, Any]]:
        """通用查询——返回结果列表。

        Args:
            domain: 知识领域（如 "accounting"）
            concept: 概念名（如 "CurrentRatio"）

        Returns:
            匹配结果列表（空列表=未命中）
        """
        self.query_count += 1
        self.queries.append((domain, concept))

        # 速率命中率控制
        if self.hit_rate < 1.0 and random.random() > self.hit_rate:
            return []

        key = f"{domain}:{concept}"
        result = self._results.get(key)
        if result is not None:
            return [result]
        return []

    def query_exact(self, domain: str, concept: str) -> dict[str, Any] | None:
        """精确查询——兼容 KnowledgeStore.query_exact()。

        Returns:
            匹配结果或 None
        """
        self.query_count += 1
        self.queries.append((domain, concept))

        if self.hit_rate < 1.0 and random.random() > self.hit_rate:
            return None

        key = f"{domain}:{concept}"
        return self._results.get(key)

    # ── 辅助方法 ──────────────────────────────────────────

    def initialize(self) -> None:
        """Mock 初始化——no-op（不插入种子数据）。"""

    def reset(self) -> None:
        """重置调用追踪状态。"""
        self.query_count = 0
        self.queries.clear()
