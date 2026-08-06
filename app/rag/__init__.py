"""
RAG 链路模块 — Embedding、向量存储、检索、索引。

组件:
    - EmbeddingClient      DashScope Embedding 封装
    - VectorStore          pgvector CRUD 操作
    - HybridRetriever      混合检索（向量 + 关键词，RRF 融合）
    - QuestionBankIndexer  题库批量向量化入库
"""

from app.rag.embeddings import EmbeddingClient, EmbeddingError, get_embedding_client
from app.rag.indexer import QuestionBankIndexer
from app.rag.retriever import HybridRetriever
from app.rag.vector_store import SearchResult, VectorStore

__all__ = [
    "EmbeddingClient",
    "EmbeddingError",
    "get_embedding_client",
    "VectorStore",
    "SearchResult",
    "HybridRetriever",
    "QuestionBankIndexer",
]
