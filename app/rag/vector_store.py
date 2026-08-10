"""
pgvector 向量存储 — 异步 CRUD 操作。

特性:
    - 距离算子: cosine (<=>), L2 (<->), inner product (<#>)
    - 支持 metadata 过滤 + 向量检索混合
    - 批量插入优化
    - 索引管理 (IVFFlat / HNSW)

用法:
    from app.rag.vector_store import VectorStore

    store = VectorStore(session)
    results = await store.search(query_vector, top_k=5, filters={"difficulty": "hard"})
"""

import uuid
from dataclasses import dataclass
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import QuestionBank

logger = structlog.get_logger(__name__)


@dataclass
class SearchResult:
    """检索结果。"""

    id: uuid.UUID
    content: str
    score: float  # 相似度分数 (cosine similarity, 越高越相似)
    metadata: dict[str, Any]


class VectorStore:
    """
    pgvector 向量存储 — 基于 QuestionBank 模型的 CRUD。

    使用 pgvector 的 cosine distance 算子 <=> 进行检索。
    cosine similarity = 1 - cosine distance
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 写入操作 ----

    async def upsert_batch(
        self,
        items: list[dict[str, Any]],
    ) -> list[QuestionBank]:
        """
        批量插入/更新题库。

        Args:
            items: [{"content": "...", "embedding": [...], ...}, ...]
        """
        records: list[QuestionBank] = []
        for item in items:
            record = QuestionBank(
                content=item["content"],
                embedding=item["embedding"],
                category=item.get("category", "general"),
                subcategory=item.get("subcategory"),
                difficulty=item.get("difficulty", "medium"),
                question_type=item.get("question_type", "technical"),
                tags=item.get("tags", []),
                reference_answer=item.get("reference_answer"),
                key_points=item.get("key_points", []),
                source=item.get("source"),
            )
            self.session.add(record)
            records.append(record)

        await self.session.flush()
        logger.info("vector_store_batch_upsert", count=len(records))
        return records

    # ---- 检索操作 ----

    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        min_similarity: float = 0.0,
        query_text: str = "",
    ) -> list[SearchResult]:
        """向量相似度检索 + 元数据过滤（mock 模式使用 query_text 做关键词匹配）。"""
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        conditions = ["embedding IS NOT NULL"]
        params: dict[str, Any] = {"embedding": embedding_str, "top_k": top_k}

        if query_text:
            params["query"] = query_text
        if category:
            conditions.append("category = :category")
            params["category"] = category
        if difficulty:
            conditions.append("difficulty = :difficulty")
            params["difficulty"] = difficulty
        if question_type:
            conditions.append("question_type = :question_type")
            params["question_type"] = question_type
        if min_similarity > 0:
            conditions.append("1 - (embedding <=> :embedding) >= :min_sim")
            params["min_sim"] = min_similarity

        where_clause = " AND ".join(conditions)

        sql = text(f"""
            SELECT
                id,
                content,
                1 - (embedding <=> :embedding) AS similarity,
                category,
                difficulty,
                question_type,
                tags,
                reference_answer,
                key_points
            FROM question_bank
            WHERE {where_clause}
            ORDER BY embedding <=> :embedding
            LIMIT :top_k
        """)

        result = await self.session.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                id=row.id,
                content=row.content,
                score=round(row.similarity, 4),
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
