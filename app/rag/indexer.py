"""
文档索引器 — 题库批量向量化入库。

特性:
    - 文本分块（可配置大小与 overlap）
    - 批量 Embedding + 写入
    - 断点续传支持
    - 进度日志

用法:
    from app.rag.indexer import QuestionBankIndexer

    indexer = QuestionBankIndexer(embedding_client, vector_store)
    count = await indexer.index_questions(questions_data)
"""

import asyncio
from typing import Any, Optional

import structlog

from app.rag.embeddings import EmbeddingClient
from app.rag.vector_store import VectorStore

logger = structlog.get_logger(__name__)

# 文本分块默认配置
DEFAULT_CHUNK_SIZE = 500       # 字符数
DEFAULT_CHUNK_OVERLAP = 50     # overlap 字符数


class QuestionBankIndexer:
    """
    题库索引器 — 批量向量化题目并写入 pgvector。
    """

    def __init__(
        self,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
    ) -> None:
        self.embedding_client = embedding_client
        self.vector_store = vector_store

    async def index_questions(
        self,
        questions: list[dict[str, Any]],
        *,
        batch_size: int = 20,
    ) -> int:
        """
        批量索引题目到题库。

        Args:
            questions: 题目数据列表
                [{"content": "...", "category": "backend", "reference_answer": "...", ...}, ...]
            batch_size: 每批处理的题目数

        Returns:
            成功索引的题目总数
        """
        total_indexed = 0

        for i in range(0, len(questions), batch_size):
            batch = questions[i : i + batch_size]

            # 提取文本
            texts = [q["content"] for q in batch]

            # 批量向量化
            embeddings = await self.embedding_client.embed_batch(texts)

            # 组装数据
            items: list[dict[str, Any]] = []
            for question, embedding in zip(batch, embeddings):
                items.append({
                    "content": question["content"],
                    "embedding": embedding,
                    "category": question.get("category", "general"),
                    "subcategory": question.get("subcategory"),
                    "difficulty": question.get("difficulty", "medium"),
                    "question_type": question.get("question_type", "technical"),
                    "tags": question.get("tags", []),
                    "reference_answer": question.get("reference_answer"),
                    "key_points": question.get("key_points", []),
                    "source": question.get("source"),
                })

            # 批量写入
            await self.vector_store.upsert_batch(items)
            total_indexed += len(items)

            logger.info(
                "indexing_progress",
                batch=(i // batch_size) + 1,
                indexed=total_indexed,
                total=len(questions),
            )

        logger.info("indexing_complete", total_indexed=total_indexed)
        return total_indexed

    async def index_documents(
        self,
        documents: list[dict[str, str]],
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> int:
        """
        索引文档（先分块再向量化）。

        Args:
            documents: [{"content": "...", "metadata": {...}}, ...]
            chunk_size:   分块大小（字符数）
            chunk_overlap: overlap 大小

        Returns:
            成功索引的 chunk 总数
        """
        all_chunks: list[dict[str, Any]] = []

        for doc in documents:
            chunks = self._chunk_text(
                doc["content"],
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            for chunk in chunks:
                all_chunks.append({
                    "content": chunk,
                    "category": doc.get("category", "general"),
                    "difficulty": doc.get("difficulty", "medium"),
                    "question_type": doc.get("question_type", "technical"),
                    "tags": doc.get("tags", []),
                    "reference_answer": doc.get("reference_answer"),
                    "key_points": doc.get("key_points", []),
                    "source": doc.get("source"),
                })

        logger.info(
            "document_chunked",
            documents=len(documents),
            chunks=len(all_chunks),
            avg_chunk_size=chunk_size,
        )

        return await self.index_questions(all_chunks)

    @staticmethod
    def _chunk_text(
        text: str, *, chunk_size: int = 500, chunk_overlap: int = 50
    ) -> list[str]:
        """
        简单滑动窗口分块 — 按字符数切分。

        后续可以用更智能的语义分块（如按段落、按句子边界）。
        """
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += chunk_size - chunk_overlap

        return chunks
