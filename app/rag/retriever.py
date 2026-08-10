"""
混合检索器 — 向量检索 + 关键词检索，RRF 融合排序。

特性:
    - 向量检索 (pgvector cosine): 语义相似，权重 W_vec
    - 关键词检索 (PostgreSQL full-text search): 精确匹配，权重 W_kw
    - RRF (Reciprocal Rank Fusion) 融合结果

用法:
    from app.rag.retriever import HybridRetriever

    retriever = HybridRetriever(vector_store, embedding_client)
    results = await retriever.retrieve("Python 中的装饰器原理", top_k=5)
"""

import uuid
from dataclasses import dataclass
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embeddings import EmbeddingClient
from app.rag.vector_store import SearchResult, VectorStore

logger = structlog.get_logger(__name__)


@dataclass
class HybridSearchResult:
    """混合检索结果。"""

    id: uuid.UUID
    content: str
    score: float  # RRF 融合分数
    vector_score: float
    keyword_score: float
    metadata: dict[str, Any]


class HybridRetriever:
    """
    混合检索器 — 向量 + 关键词两路召回，RRF 融合。

    检索流程:
        1. 查询向量化 (Embedding)
        2. 向量检索 → top_k * 2 候选
        3. 关键词检索 → top_k * 2 候选
        4. RRF 融合排序 → top_k 结果
    """

    # RRF 融合参数
    RRF_K = 60  # RRF 平滑常数

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_client: EmbeddingClient,
        *,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        min_similarity: float = 0.0,
    ) -> list[HybridSearchResult]:
        """
        混合检索入口。

        Args:
            query:          查询文本
            top_k:          返回数量
            category:       类别过滤
            difficulty:     难度过滤
            question_type:  题型过滤
            min_similarity: 最低相似度阈值

        Returns:
            HybridSearchResult 列表，按 RRF 融合分降序
        """
        # 1. 查询向量化
        query_embedding = await self.embedding_client.embed_single(query)

        # 2. 向量检索（召回 top_k * 2 候选）
        vector_results = await self.vector_store.search(
            query_embedding,
            top_k=top_k * 2,
            category=category,
            difficulty=difficulty,
            question_type=question_type,
            min_similarity=min_similarity,
            query_text=query,
        )

        # 3. 关键词检索（并行）
        keyword_results = await self._keyword_search(
            query, top_k=top_k * 2,
            category=category, difficulty=difficulty, question_type=question_type,
        )

        # 4. RRF 融合
        merged = self._rrf_fusion(vector_results, keyword_results, top_k)

        return merged

    async def _keyword_search(
        self,
        query: str,
        top_k: int = 10,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        PostgreSQL 全文检索 — 使用 tsvector/tsquery 进行关键词匹配。
        """
        conditions = ["to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)"]
        params: dict[str, Any] = {"query": query, "top_k": top_k}

        if category:
            conditions.append("category = :category")
            params["category"] = category
        if difficulty:
            conditions.append("difficulty = :difficulty")
            params["difficulty"] = difficulty
        if question_type:
            conditions.append("question_type = :question_type")
            params["question_type"] = question_type

        where_clause = " AND ".join(conditions)

        sql = text(f"""
            SELECT
                id,
                content,
                ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', :query)) AS rank,
                category,
                difficulty,
                question_type,
                tags,
                reference_answer,
                key_points
            FROM question_bank
            WHERE {where_clause}
            ORDER BY rank DESC
            LIMIT :top_k
        """)

        result = await self.vector_store.session.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                id=row.id,
                content=row.content,
                score=round(row.rank, 4),
                metadata={
                    "category": row.category,
                    "difficulty": row.difficulty,
                    "question_type": row.question_type,
                    "tags": row.tags,
                    "reference_answer": row.reference_answer,
                    "key_points": row.key_points,
                },
            )
            for row in rows
        ]

    def _rrf_fusion(
        self,
        vector_results: list[SearchResult],
        keyword_results: list[SearchResult],
        top_k: int,
    ) -> list[HybridSearchResult]:
        """
        Reciprocal Rank Fusion 融合两路检索结果。

        RRF_score(doc) = Σ W_i / (k + rank_i)
        其中 k 是平滑常数，rank_i 是文档在第 i 路中的排名。
        """
        # 记录每路的排名
        vector_ranks: dict[uuid.UUID, int] = {}
        for rank, r in enumerate(vector_results, start=1):
            vector_ranks[r.id] = rank

        keyword_ranks: dict[uuid.UUID, int] = {}
        for rank, r in enumerate(keyword_results, start=1):
            keyword_ranks[r.id] = rank

        # 合并文档信息
        docs: dict[uuid.UUID, dict[str, Any]] = {}
        for r in vector_results:
            docs[r.id] = {
                "content": r.content,
                "vector_score": r.score,
                "keyword_score": 0.0,
                "metadata": r.metadata,
            }
        for r in keyword_results:
            if r.id in docs:
                docs[r.id]["keyword_score"] = r.score
            else:
                docs[r.id] = {
                    "content": r.content,
                    "vector_score": 0.0,
                    "keyword_score": r.score,
                    "metadata": r.metadata,
                }

        # 计算 RRF 分数
        rrf_scores: dict[uuid.UUID, float] = {}
        for doc_id in docs:
            vec_rank = vector_ranks.get(doc_id, len(vector_results) + 1)
            kw_rank = keyword_ranks.get(doc_id, len(keyword_results) + 1)

            rrf = (
                self.vector_weight / (self.RRF_K + vec_rank)
                + self.keyword_weight / (self.RRF_K + kw_rank)
            )
            rrf_scores[doc_id] = rrf

        # 排序取 top_k
        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:top_k]

        return [
            HybridSearchResult(
                id=doc_id,
                content=docs[doc_id]["content"],
                score=round(rrf_scores[doc_id], 6),
                vector_score=docs[doc_id]["vector_score"],
                keyword_score=docs[doc_id]["keyword_score"],
                metadata=docs[doc_id]["metadata"],
            )
            for doc_id in sorted_ids
        ]
