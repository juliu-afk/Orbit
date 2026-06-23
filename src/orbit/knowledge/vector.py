"""Step 3.4c 向量语义检索——纯 Python TF-IDF。

WHY 纯 Python 而非 Qdrant/scikit-learn：
MVP 阶段零外部依赖。TF-IDF 足够支撑语义检索原型。
3.4d 迁移到 Qdrant 时接口不变（VectorStore 统一抽象）。
"""

from __future__ import annotations

import math
import re
from typing import Any

import structlog

from orbit.knowledge.store import KnowledgeStore

logger = structlog.get_logger()


def _tokenize(text: str) -> list[str]:
    """中文简单分词——按字符 bigram + 英文单词。

    WHY bigram 而非 jieba：零依赖，会计概念短文本足够。
    """
    # 提取中文字符 bigram
    chinese = re.findall(r"[一-鿿]+", text)
    tokens: list[str] = []
    for segment in chinese:
        tokens.extend(segment[i : i + 2] for i in range(len(segment) - 1))
    # 英文单词（小写）——同时保留原始版本（用于精确匹配如 ROE/EBITDA）
    english = re.findall(r"[a-zA-Z]+", text.lower())
    tokens.extend(english)
    # 同时加入原始英文单词作为 token（不做 lower，匹配概念名）
    tokens.extend(re.findall(r"[A-Z]{2,}", text))
    return tokens


class VectorStore:
    """纯 Python TF-IDF 向量存储。

    构建概念→文档索引，semantic 模式计算余弦相似度。
    """

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self._store = store or KnowledgeStore()
        if self._store.count() == 0:
            self._store.initialize()
        # TF-IDF 索引
        self._documents: dict[str, dict[str, Any]] = {}  # concept → doc
        self._idf: dict[str, float] = {}  # term → idf
        self._build_index()

    def _build_index(self) -> None:
        """构建 TF-IDF 索引。

        WHY 全量重建：MVP 阶段知识库只读，无需增量更新。
        """
        docs = {}
        df: dict[str, int] = {}  # document frequency

        for c in self._store.list_by_domain("accounting"):
            concept = c["concept"]
            row = self._store.query_exact("accounting", concept)
            if row is None:
                continue
            text = f"{concept} {row['name_zh']} {row['definition']} {row['formula']}"
            tokens = _tokenize(text)
            docs[concept] = {
                "name_zh": row["name_zh"],
                "definition": row["definition"],
                "formula": row.get("formula", ""),
                "source_uri": row["source_uri"],
                "tokens": tokens,
                "tf": self._compute_tf(tokens),
            }
            # 更新 document frequency
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        n_docs = len(docs)
        # IDF = log(N / df)
        self._idf = {
            term: math.log(n_docs / (freq + 1)) + 1
            for term, freq in df.items()
        }
        self._documents = docs
        logger.info("vector_index_built", documents=n_docs, terms=len(self._idf))

    @staticmethod
    def _compute_tf(tokens: list[str]) -> dict[str, float]:
        """词频（TF）——归一化。"""
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        max_freq = max(tf.values()) if tf else 1
        return {t: f / max_freq for t, f in tf.items()}

    def search(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """语义检索——TF-IDF 余弦相似度排序。

        Args:
            query: 自然语言查询
            top_k: 返回前 K 个结果

        Returns:
            [{concept, name_zh, definition, score, source_uri}, ...]
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # 查询 TF
        query_tf = self._compute_tf(query_tokens)

        scores: list[tuple[str, float]] = []
        for concept, doc in self._documents.items():
            score = self._cosine_similarity(query_tf, doc["tf"])
            if score > 0:
                scores.append((concept, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
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

    def _cosine_similarity(
        self, query_tf: dict[str, float], doc_tf: dict[str, float]
    ) -> float:
        """TF-IDF 加权余弦相似度。"""
        # 只计算查询中出现的 term
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
