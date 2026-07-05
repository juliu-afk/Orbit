"""向量语义检索——turbovec 索引 + BGE 嵌入 + TF-IDF 降级。

v2: turboVec 零训练量化替代纯 Python TF-IDF。
v1 (fallback): 中文 bigram TF-IDF，零外部依赖。

turbovec 来源: RyanCodrai/turbovec (MIT)，TurboQuant (ICLR 2026)。
16x 压缩（2-bit 模式），ARM/x86 SIMD 加速，零训练，与输入数据无关。
BGE 模型: BAAI/bge-small-zh-v1.5，512-dim，~100MB 首次下载缓存。

降级链路: turbovec+BGE → TF-IDF（纯 Python）
BGE 模型未下载 / turbovec 未安装 → 自动降级为 TF-IDF，不抛异常。
"""

from __future__ import annotations

import math
import re
from typing import Any

import structlog

from orbit.knowledge.store import KnowledgeStore

logger = structlog.get_logger("orbit.knowledge.vector")


# ── TF-IDF fallback tokenizer ──────────────────────────────


def _tokenize(text: str) -> list[str]:
    """中文 bigram + 英文单词分词——零依赖。"""
    chinese = re.findall(r"[一-鿿]+", text)
    tokens: list[str] = []
    for segment in chinese:
        tokens.extend(segment[i : i + 2] for i in range(len(segment) - 1))
    english = re.findall(r"[a-zA-Z]+", text.lower())
    tokens.extend(english)
    tokens.extend(re.findall(r"[A-Z]{2,}", text))
    return tokens


# ── VectorStore ────────────────────────────────────────────


class VectorStore:
    """语义向量存储——turbovec 优先，TF-IDF 降级。

    接口不变: search(query, top_k) → [{concept, name_zh, definition, score, ...}]
    """

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self._store = store or KnowledgeStore()
        if self._store.count() == 0:
            self._store.initialize()

        # turbovec 状态
        self._index: Any = None        # TurboQuantIndex
        self._embedder: Any = None     # BGEEmbeddingGenerator
        self._concepts: list[str] = []  # 槽位 → 概念名

        # TF-IDF fallback 状态
        self._documents: dict[str, dict[str, Any]] = {}
        self._idf: dict[str, float] = {}
        self._use_turbovec = False

        self._build_index()

    # ── 索引构建 ──────────────────────────────────────────

    def _build_index(self) -> None:
        """构建向量索引——turbovec 优先，失败降级 TF-IDF。"""
        # 提取知识库条目
        entries: list[dict[str, Any]] = []
        for c in self._store.list_by_domain("accounting"):
            row = self._store.query_exact("accounting", c["concept"])
            if row is None:
                continue
            entries.append({
                "concept": c["concept"],
                "name_zh": row["name_zh"],
                "definition": row["definition"],
                "formula": row.get("formula", ""),
                "source_uri": row["source_uri"],
            })

        if not entries:
            logger.info("vector_index_empty")
            return

        # 尝试 turbovec + BGE
        if self._try_turbovec(entries):
            return

        # 降级：TF-IDF
        self._build_tfidf(entries)

    def _try_turbovec(self, entries: list[dict[str, Any]]) -> bool:
        """尝试用 turbovec + BGE 构建索引。成功返回 True。"""
        try:
            import numpy as np
            from turbovec import TurboQuantIndex

            from orbit.knowledge.embedding import BGEEmbeddingGenerator
        except ImportError as e:
            logger.info("turbovec_unavailable_fallback_tfidf", reason=str(e))
            return False

        try:
            embedder = BGEEmbeddingGenerator()
            texts = [
                f"{e['concept']} {e['name_zh']} {e['definition']} {e['formula']}"
                for e in entries
            ]
            embeddings = embedder.encode(texts)
        except Exception as e:
            logger.warning("bge_encode_failed_fallback_tfidf", error=str(e))
            return False

        try:
            index = TurboQuantIndex(dim=embedder.dim, bit_width=4)
            index.add(np.array(embeddings, dtype=np.float32))
        except Exception as e:
            logger.warning("turbovec_index_failed_fallback_tfidf", error=str(e))
            return False

        self._index = index
        self._embedder = embedder
        self._concepts = [e["concept"] for e in entries]
        # 保留文档元数据 + TF 数据（供 TF-IDF fallback 使用）
        self._documents = {}
        for e in entries:
            text = f"{e['concept']} {e['name_zh']} {e['definition']} {e['formula']}"
            self._documents[e["concept"]] = {
                **e,
                "tokens": _tokenize(text),
                "tf": self._compute_tf(_tokenize(text)),
            }
        self._use_turbovec = True
        logger.info(
            "turbovec_index_built",
            entries=len(entries),
            dim=embedder.dim,
            compression="4-bit (8x)",
        )
        return True

    def _build_tfidf(self, entries: list[dict[str, Any]]) -> None:
        """降级：纯 Python TF-IDF 索引。"""
        docs: dict[str, dict[str, Any]] = {}
        df: dict[str, int] = {}

        for e in entries:
            text = f"{e['concept']} {e['name_zh']} {e['definition']} {e['formula']}"
            tokens = _tokenize(text)
            docs[e["concept"]] = {
                **e,
                "tokens": tokens,
                "tf": self._compute_tf(tokens),
            }
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        n_docs = len(docs)
        self._idf = {
            term: math.log(n_docs / (freq + 1)) + 1
            for term, freq in df.items()
        }
        self._documents = docs
        self._use_turbovec = False
        logger.info("tfidf_index_built", documents=n_docs, terms=len(self._idf))

    # ── 搜索 ──────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """语义检索——turbovec 优先，TF-IDF 降级。

        Args:
            query: 自然语言查询
            top_k: 返回前 K 个结果

        Returns:
            [{concept, name_zh, definition, formula, score, source_uri}, ...]
        """
        if not query.strip():
            return []
        if self._use_turbovec and self._index is not None:
            return self._search_turbovec(query, top_k)
        return self._search_tfidf(query, top_k)

    def _search_turbovec(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """turbovec 语义搜索。"""
        import numpy as np

        try:
            query_vec = np.array(
                [self._embedder.encode_query(query)], dtype=np.float32
            )
            scores, indices = self._index.search(query_vec, k=min(top_k, len(self._concepts)))
            # turbovec returns 2D results for batch queries
            scores = scores[0] if scores.ndim == 2 else scores
            indices = indices[0] if indices.ndim == 2 else indices
        except Exception as e:
            logger.warning("turbovec_search_failed_fallback_tfidf", error=str(e))
            return self._search_tfidf(query, top_k)

        results: list[dict[str, Any]] = []
        for slot, score in zip(indices, scores):
            if slot < 0 or slot >= len(self._concepts):
                continue
            concept = self._concepts[slot]
            doc = self._documents.get(concept, {})
            results.append({
                "concept": concept,
                "name_zh": doc.get("name_zh", ""),
                "definition": doc.get("definition", ""),
                "formula": doc.get("formula", ""),
                "score": round(float(score), 4),
                "source_uri": doc.get("source_uri", ""),
            })

        return results

    def _search_tfidf(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """TF-IDF 关键词搜索（降级）。"""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_tf = self._compute_tf(query_tokens)
        scores: list[tuple[str, float]] = []
        for concept, doc in self._documents.items():
            score = self._cosine_similarity(query_tf, doc["tf"])
            if score > 0:
                scores.append((concept, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results: list[dict[str, Any]] = []
        for concept, score in scores[:top_k]:
            doc = self._documents[concept]
            results.append({
                "concept": concept,
                "name_zh": doc["name_zh"],
                "definition": doc["definition"],
                "formula": doc.get("formula", ""),
                "score": round(score, 4),
                "source_uri": doc["source_uri"],
            })

        return results

    # ── 内部 ──────────────────────────────────────────────

    @staticmethod
    def _compute_tf(tokens: list[str]) -> dict[str, float]:
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        max_freq = max(tf.values()) if tf else 1
        return {t: f / max_freq for t, f in tf.items()}

    def _cosine_similarity(
        self, query_tf: dict[str, float], doc_tf: dict[str, float]
    ) -> float:
        dot = 0.0
        query_norm = 0.0
        doc_norm = 0.0
        all_terms = set(query_tf) | set(doc_tf)
        for term in all_terms:
            qw = query_tf.get(term, 0) * self._idf.get(term, 1)
            dw = doc_tf.get(term, 0) * self._idf.get(term, 1)
            dot += qw * dw
            query_norm += qw * qw
            doc_norm += dw * dw
        if query_norm == 0 or doc_norm == 0:
            return 0.0
        return dot / (math.sqrt(query_norm) * math.sqrt(doc_norm))
