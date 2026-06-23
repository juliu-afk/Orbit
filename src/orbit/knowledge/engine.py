"""Step 3.4b 知识查询引擎——统一查询接口。

支持三种模式：
- exact: Neo4j/SQLite 精确查询（当前 SQLite，零 Token，<50ms）
- semantic: 向量语义检索（3.4c 实现，当前 stub）
- hybrid: 图谱锚定 + 向量扩展（3.4c 实现，当前降级为 exact）
"""

from __future__ import annotations

from typing import Any, Literal

import structlog

from orbit.knowledge.store import KnowledgeStore

logger = structlog.get_logger()

QueryMode = Literal["exact", "semantic", "hybrid"]


class QueryResult:
    """统一查询结果。"""

    def __init__(
        self,
        content: str,
        source_uri: str,
        confidence: float,
        mode_used: str,
    ) -> None:
        self.content = content
        self.source_uri = source_uri
        self.confidence = confidence
        self.mode_used = mode_used

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "source_uri": self.source_uri,
            "confidence": self.confidence,
            "mode_used": self.mode_used,
        }


class KnowledgeEngine:
    """知识查询引擎。

    包装 KnowledgeStore，提供 exact/semantic/hybrid 统一接口。
    """

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self._store = store or KnowledgeStore()
        if self._store.count() == 0:
            self._store.initialize()

    def query(
        self,
        domain: str,
        concept: str,
        mode: QueryMode = "exact",
    ) -> QueryResult | None:
        """按领域+概念查询。

        exact 模式：直接 SQLite 查，零 LLM Token。
        semantic/hybrid：3.4c 实现。
        """
        if mode in ("semantic", "hybrid"):
            # 3.4c 实现前降级为 exact
            logger.info(
                "query_mode_degraded",
                mode=mode,
                fallback="exact",
                reason="3.4c not yet implemented",
            )

        row = self._store.query_exact(domain, concept)
        if row is None:
            return None

        # 构建 content：定义 + 公式（如有）
        parts = [f"## {row['name_zh']} ({row['concept']})", row["definition"]]
        if row.get("formula"):
            parts.append(f"公式：{row['formula']}")

        return QueryResult(
            content="\n\n".join(parts),
            source_uri=row["source_uri"],
            confidence=1.0,  # exact 模式 100% 置信
            mode_used=mode,
        )

    def list_concepts(self, domain: str) -> list[dict[str, Any]]:
        """列出某领域所有概念（简要）。"""
        return self._store.list_by_domain(domain)

    def count(self) -> int:
        """概念总数。"""
        return self._store.count()
