"""记忆向量语义搜索 + RRF 混合融合 (V15.2).

在现有 BM25 关键词搜索基础上增加 BGE 向量语义搜索，
通过 RRF (Reciprocal Rank Fusion) 融合两个排序结果。

WHY RRF: 简单、零参数（仅 k=60）、实践中优于线性加权。
BM25 擅长精确关键词匹配，向量搜索擅长语义理解——
RRF 让两者互补。

依赖: 复用 knowledge/embedding.py 的 BGEEmbedder（单例），零新模型加载。
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from orbit.knowledge.embedding import EmbeddingGenerator

logger = structlog.get_logger("orbit.memory.vector")

# RRF 融合参数——k=60 是信息检索领域标准值
RRF_K = 60


class MemoryVectorIndex:
    """记忆向量索引——与 BM25 配合做 RRF 混合检索。

    存储: SQLite 表存向量（JSON 数组）。
    MVP 阶段避免引入 FAISS/chroma 等重依赖。
    数据量 <10K 条时线性扫描余弦相似度足够快（~5ms/1000 条）。

    Usage:
        idx = MemoryVectorIndex(embedder, ":memory:")
        idx.index("mem_001", "应收账款坏账调整因截止性问题被否定")
        results = idx.search("审计调整为什么失败", top_k=10)
        # → [("mem_001", 0.87), ...]
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS memory_vectors (
        memory_id TEXT PRIMARY KEY,
        vector_json TEXT NOT NULL,
        text_preview TEXT NOT NULL DEFAULT '',
        indexed_at REAL NOT NULL
    );
    """

    def __init__(
        self,
        embedder: "EmbeddingGenerator | None" = None,
        db_path: str = ":memory:",
    ) -> None:
        self._embedder = embedder
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()

    @property
    def is_ready(self) -> bool:
        """嵌入器是否就绪——未就绪时 search() 返回空，调用方回退纯 BM25。"""
        return self._embedder is not None

    def index(self, memory_id: str, text: str) -> None:
        """索引一段记忆文本——生成向量并存入 SQLite。

        Args:
            memory_id: 记忆唯一标识（与 MemoryStore 对齐）
            text: 记忆文本——截取前 2000 字符做向量化
        """
        if not self._embedder or not text.strip():
            return

        try:
            # 取前 2000 字符——记忆段落通常 <500 字，2000 足够覆盖
            truncated = text.strip()[:2000]
            vectors = self._embedder.encode([truncated])
            if not vectors or not vectors[0]:
                return

            self._db.execute(
                """INSERT OR REPLACE INTO memory_vectors
                   (memory_id, vector_json, text_preview, indexed_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    memory_id,
                    json.dumps(vectors[0]),
                    truncated[:200],
                    time.time(),
                ),
            )
            self._db.commit()
            logger.debug("vector_indexed", memory_id=memory_id)

        except Exception as e:
            logger.warning("vector_index_failed", memory_id=memory_id, error=str(e)[:100])

    def search(
        self, query: str, top_k: int = 20
    ) -> list[tuple[str, float]]:
        """余弦相似度搜索——返回 [(memory_id, score), ...] 按分数降序。

        Args:
            query: 搜索查询
            top_k: 返回前 K 个结果
        """
        if not self._embedder:
            return []

        try:
            query_vec = self._embedder.encode_query(query)
            if not query_vec:
                return []

            rows = self._db.execute(
                "SELECT memory_id, vector_json FROM memory_vectors"
            ).fetchall()

            scored: list[tuple[str, float]] = []
            for row in rows:
                vec = json.loads(row["vector_json"])
                sim = _cosine_similarity(query_vec, vec)
                if sim > 0:
                    scored.append((row["memory_id"], sim))

            scored.sort(key=lambda x: -x[1])
            return scored[:top_k]

        except Exception as e:
            logger.warning("vector_search_failed", error=str(e)[:100])
            return []

    def rebuild(self) -> None:
        """清空并重建向量索引——文件记忆变更后调用。"""
        self._db.execute("DELETE FROM memory_vectors")
        self._db.commit()
        logger.info("vector_index_rebuilt")

    def count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._db.close()


def rrf_fusion(
    ranked_a: list[tuple[str, float]],
    ranked_b: list[tuple[str, float]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """RRF 融合两个排序列表——返回按 RRF 分数降序的结果。

    RRF 公式: score(id) = Σ 1/(k + rank_i(id))

    Args:
        ranked_a: 第一个排序列表 [(id, score), ...]
        ranked_b: 第二个排序列表 [(id, score), ...]
        k: RRF 参数——默认 60

    Returns:
        [(id, rrf_score), ...] 按 RRF 分数降序

    WHY k=60: TREC/信息检索社区的实证最优值。
    k 越小 → 排名影响越大（top-1 vs top-2 差距大）；
    k 越大 → 排名影响越小（top-10 vs top-11 差距小）。
    """
    scores: dict[str, float] = {}

    for rank, (item_id, _) in enumerate(ranked_a):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, (item_id, _) in enumerate(ranked_b):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda x: -x[1])


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度——纯 Python，零依赖。"""
    if len(a) != len(b) or len(a) == 0:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)
