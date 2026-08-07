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
from app.rag.embeddings import EMBEDDING_DIMENSION

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

    # 索引类型常量
    INDEX_IVFFLAT = "ivfflat"
    INDEX_HNSW = "hnsw"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 写入操作 ----

    async def upsert(
        self,
        content: str,
        embedding: list[float],
        *,
        question_id: Optional[uuid.UUID] = None,
        category: str = "general",
        subcategory: Optional[str] = None,
        difficulty: str = "medium",
        question_type: str = "technical",
        tags: Optional[list[str]] = None,
        reference_answer: Optional[str] = None,
        key_points: Optional[list[str]] = None,
        source: Optional[str] = None,
    ) -> QuestionBank:
        """插入或更新一条题库记录。"""
        if question_id:
            record = await self.session.get(QuestionBank, question_id)
            if record is None:
                raise ValueError(f"QuestionBank {question_id} not found")
            record.content = content
            record.embedding = embedding
            record.category = category
            record.subcategory = subcategory
            record.difficulty = difficulty
            record.question_type = question_type
            record.tags = tags or []
            record.reference_answer = reference_answer
            record.key_points = key_points or []
            record.source = source
        else:
            record = QuestionBank(
                content=content,
                embedding=embedding,
                category=category,
                subcategory=subcategory,
                difficulty=difficulty,
                question_type=question_type,
                tags=tags or [],
                reference_answer=reference_answer,
                key_points=key_points or [],
                source=source,
            )
            self.session.add(record)

        await self.session.flush()
        return record

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

    # ---- 索引管理 ----

    async def create_index(
        self, index_type: str = INDEX_IVFFLAT, n_lists: int = 100
    ) -> None:
        """
        创建向量索引以加速检索。

        IVFFlat: 适合 < 1M 数据量，构建快
        HNSW:    适合 > 1M 数据量，检索更快但构建慢
        """
        if index_type == self.INDEX_IVFFLAT:
            sql = text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_question_bank_embedding_ivfflat
                ON question_bank USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {n_lists})
            """
            )
        elif index_type == self.INDEX_HNSW:
            sql = text(
                """
                CREATE INDEX IF NOT EXISTS idx_question_bank_embedding_hnsw
                ON question_bank USING hnsw (embedding vector_cosine_ops)
            """
            )
        else:
            raise ValueError(f"Unknown index type: {index_type}")

        await self.session.execute(sql)
        await self.session.commit()
        logger.info("vector_index_created", type=index_type)

    async def count(self) -> int:
        """获取已向量化的记录数。"""
        result = await self.session.execute(
            text("SELECT COUNT(*) FROM question_bank WHERE embedding IS NOT NULL")
        )
        return result.scalar() or 0

    # ---- 删除 ----

    async def delete(self, question_id: uuid.UUID) -> bool:
        """删除一条题库记录。"""
        record = await self.session.get(QuestionBank, question_id)
        if record is None:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True

    async def delete_by_ids(self, ids: list[uuid.UUID]) -> int:
        """批量删除。"""
        result = await self.session.execute(
            text("DELETE FROM question_bank WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await self.session.flush()
        return result.rowcount or 0
