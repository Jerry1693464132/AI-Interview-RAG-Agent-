"""
RAG 链路模块 — Embedding、向量存储、检索。

组件:
    - EmbeddingClient      DashScope Embedding 封装
    - VectorStore          pgvector CRUD 操作
    - HybridRetriever      混合检索（向量 + 关键词，RRF 融合）
"""

from app.rag.embeddings import EmbeddingClient, EmbeddingError, get_embedding_client
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import SearchResult, VectorStore

__all__ = [
    "EmbeddingClient",
    "EmbeddingError",
    "get_embedding_client",
    "VectorStore",
    "SearchResult",
    "HybridRetriever",
]
