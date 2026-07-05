"""嵌入向量生成器抽象——支持本地模型和远程 API 互换。

对标 turboVec 零训练量化管线: 嵌入生成与向量索引解耦。
默认 BGE-small-zh-v1.5 本地模型——零网络依赖，符合 Tauri 桌面部署约束。

Usage:
    gen = BGEEmbeddingGenerator()
    vectors = gen.encode(["文本1", "文本2"])       # → [[0.1, ...], ...]
    query_vec = gen.encode_query("搜索词")          # → [0.1, ...]
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger("orbit.knowledge.embedding")


class EmbeddingGenerator(ABC):
    """嵌入向量生成器抽象基类。

    子类:
    - BGEEmbeddingGenerator: 本地 BGE 模型（默认）
    - OpenAIEmbeddingGenerator: 远程 API（可选）
    """

    dim: int  # 向量维度——子类覆盖

    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量列表。用于索引构建。"""
        ...

    @abstractmethod
    def encode_query(self, query: str) -> list[float]:
        """单条查询文本 → 向量。用于搜索。"""
        ...


class BGEEmbeddingGenerator(EmbeddingGenerator):
    """BGE-small-zh-v1.5 本地嵌入——零网络依赖。

    首次使用自动下载模型（~100MB），缓存到 ~/.cache/huggingface/。
    中英双语，512 维向量。

    WHY BGE-small-zh-v1.5:
    - 中文 + 英文混合场景最优性价比（质量接近大模型，体积仅 ~100MB）
    - 512 维比 768/1024 维度更紧凑，turbovec 压缩比更高
    - BGE 系列查询需前缀 "为这个句子生成表示以用于检索相关文章："

    降级策略: sentence-transformers 未安装或模型下载失败 → EmbeddingError。
    调用方应 catch 后回退到 TF-IDF。
    """

    dim = 512
    _MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    _QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F811
        except ImportError as e:
            raise EmbeddingError(
                "sentence-transformers 未安装。运行: pip install sentence-transformers"
            ) from e

        try:
            self._model = SentenceTransformer(self._MODEL_NAME)
            logger.info(
                "bge_model_loaded",
                model=self._MODEL_NAME,
                dim=self.dim,
            )
        except Exception as e:
            raise EmbeddingError(
                f"BGE 模型加载失败 ({self._MODEL_NAME}): {e}"
            ) from e

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # BGE 模型指令: 文档编码不需要前缀
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def encode_query(self, query: str) -> list[float]:
        # BGE 模型指令: 查询编码需要前缀
        embedding = self._model.encode(
            self._QUERY_PREFIX + query,
            normalize_embeddings=True,
        )
        return embedding.tolist()


class EmbeddingError(Exception):
    """嵌入生成失败——调用方应降级到 TF-IDF。"""
    pass
