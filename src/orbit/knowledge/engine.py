"""Step 3.4b/c 知识查询引擎——统一查询接口。

三种模式：
- exact: SQLite 精确查询（零 Token，<50ms）
- semantic: TF-IDF 向量语义检索（3.4c）
- hybrid: 图谱锚定 + 向量扩展（3.4c）
"""

from __future__ import annotations

from typing import Any, Literal

import structlog

from orbit.knowledge.store import KnowledgeStore
from orbit.knowledge.vector import VectorStore

logger = structlog.get_logger("orbit.knowledge.engine")

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

    包装 KnowledgeStore + VectorStore，提供 exact/semantic/hybrid 统一接口。
    """

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._store = store or KnowledgeStore()
        # WHY 无条件 initialize：_get_conn() 已自动建表，initialize()
        # 负责种子数据导入。INSERT OR IGNORE 保证幂等。
        self._store.initialize()
        # 惰性初始化 VectorStore（只在 semantic/hybrid 模式需要）
        self._vector: VectorStore | None = vector_store

    def _get_vector(self) -> VectorStore:
        if self._vector is None:
            self._vector = VectorStore(store=self._store)
        return self._vector

    def query(
        self,
        domain: str,
        concept: str,
        mode: QueryMode = "exact",
    ) -> QueryResult | None:
        """按领域+概念查询。

        exact: 直接 SQLite，confidence=1.0。
        semantic: TF-IDF 向量检索，confidence=score。
        hybrid: exact 锚定 + semantic 扩展。
        """
        if mode == "exact":
            return self._query_exact(domain, concept)
        if mode == "semantic":
            return self._query_semantic(concept)
        # hybrid: exact first, fallback to semantic
        result = self._query_exact(domain, concept)
        if result is not None:
            return result
        return self._query_semantic(concept)

    def _query_exact(self, domain: str, concept: str) -> QueryResult | None:
        row = self._store.query_exact(domain, concept)
        if row is None:
            return None

        parts = [f"## {row['name_zh']} ({row['concept']})", row["definition"]]
        if row.get("formula"):
            parts.append(f"公式：{row['formula']}")

        return QueryResult(
            content="\n\n".join(parts),
            source_uri=row["source_uri"],
            confidence=1.0,
            mode_used="exact",
        )

    def _query_semantic(self, concept: str) -> QueryResult | None:
        """语义检索——用概念名作为查询词搜索 TF-IDF 索引。"""
        vector = self._get_vector()
        results = vector.search(concept, top_k=1)
        if not results:
            return None

        top = results[0]
        # score 低于 0.1 视为不相关
        if top["score"] < 0.1:
            return None

        parts = [f"## {top['name_zh']} ({top['concept']})", top["definition"]]
        if top.get("formula"):
            parts.append(f"公式：{top['formula']}")

        return QueryResult(
            content="\n\n".join(parts),
            source_uri=top["source_uri"],
            confidence=top["score"],
            mode_used="semantic",
        )

    def query_structured(self, domain: str, concept: str) -> dict[str, Any]:
        """返回结构化 dict——供 tool handler 使用（Inkeep 借鉴 #3）。

        WHY 独立方法: 现有 query() 返回 QueryResult 对象（内部用），
        tool handler 需要 JSON-serializable dict 直接返回给 Agent。
        """
        result = self.query(domain, concept, mode="hybrid")
        if result is None or result.confidence < 0.3:
            # 语义搜索置信度 < 0.3 → 视为未找到，避免模糊匹配误报
            return {
                "found": False,
                "message": f"概念 '{concept}' 在领域 '{domain}' 中未找到",
            }
        return {
            "found": True,
            "content": result.content,
            "source_uri": result.source_uri,
            "confidence": result.confidence,
            "mode_used": result.mode_used,
        }

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """开放语义搜索——直接暴露 VectorStore.search。"""
        return self._get_vector().search(query, top_k=top_k)

    def list_concepts(self, domain: str) -> list[dict[str, Any]]:
        return self._store.list_by_domain(domain)

    def count(self) -> int:
        return self._store.count()
