"""
题库管理 API。

API:
    GET    /questions/              — 题目列表
    POST   /questions/              — 新增题目（自动向量化）
    GET    /questions/{id}          — 题目详情
    DELETE /questions/{id}          — 删除题目
    POST   /questions/search        — 语义检索（RAG）
    POST   /questions/batch-index   — 批量索引
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.models.question import QuestionBank
from app.rag.embeddings import get_embedding_client
from app.rag.vector_store import VectorStore
from app.schemas.common import APIResponse
from app.schemas.question import (
    QuestionBankCreateRequest,
    QuestionResponse,
    QuestionSearchRequest,
)

router = APIRouter()


@router.get("/", response_model=APIResponse[list[QuestionResponse]])
async def list_questions(
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """列出题库题目。"""
    from sqlalchemy import select

    stmt = select(QuestionBank).order_by(QuestionBank.created_at.desc())
    if category:
        stmt = stmt.where(QuestionBank.category == category)
    if difficulty:
        stmt = stmt.where(QuestionBank.difficulty == difficulty)
    if question_type:
        stmt = stmt.where(QuestionBank.question_type == question_type)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    questions = result.scalars().all()

    return APIResponse(
        data=[
            QuestionResponse(
                id=q.id,
                content=q.content,
                question_type=q.question_type,
                difficulty=q.difficulty,
                order_index=0,
                reference_answer=q.reference_answer,
                key_points=q.key_points or [],
            )
            for q in questions
        ]
    )


@router.post("/", response_model=APIResponse[QuestionResponse], status_code=201)
async def create_question(
    request: QuestionBankCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """新增题目，自动生成 Embedding 并写入向量存储。"""
    # 生成 Embedding
    embedding_client = get_embedding_client()
    embedding = await embedding_client.embed_single(request.content)

    # 写入向量存储
    store = VectorStore(db)
    record = await store.upsert(
        content=request.content,
        embedding=embedding,
        category=request.category,
        subcategory=request.subcategory,
        difficulty=request.difficulty,
        question_type=request.question_type,
        tags=request.tags,
        reference_answer=request.reference_answer,
        key_points=request.key_points,
        source=request.source,
    )

    return APIResponse(
        data=QuestionResponse(
            id=record.id,
            content=record.content,
            question_type=record.question_type,
            difficulty=record.difficulty,
            order_index=0,
            reference_answer=record.reference_answer,
            key_points=record.key_points or [],
        )
    )


@router.get("/{question_id}", response_model=APIResponse[QuestionResponse])
async def get_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取题目详情。"""
    question = await db.get(QuestionBank, question_id)
    if not question:
        raise NotFoundError("QuestionBank", question_id)

    return APIResponse(
        data=QuestionResponse(
            id=question.id,
            content=question.content,
            question_type=question.question_type,
            difficulty=question.difficulty,
            order_index=0,
            reference_answer=question.reference_answer,
            key_points=question.key_points or [],
        )
    )


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除题目。"""
    question = await db.get(QuestionBank, question_id)
    if not question:
        raise NotFoundError("QuestionBank", question_id)
    await db.delete(question)
    await db.commit()


@router.post("/search", response_model=APIResponse[list[dict]])
async def search_questions(
    request: QuestionSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """语义检索题目（RAG 链路）。"""
    from app.rag.retriever import HybridRetriever

    embedding_client = get_embedding_client()
    store = VectorStore(db)
    retriever = HybridRetriever(store, embedding_client)

    results = await retriever.retrieve(
        query=request.query,
        top_k=request.top_k,
        category=request.category,
        difficulty=request.difficulty,
        question_type=request.question_type,
    )

    return APIResponse(
        data=[
            {
                "id": str(r.id),
                "content": r.content,
                "score": r.score,
                "vector_score": r.vector_score,
                "keyword_score": r.keyword_score,
                "metadata": r.metadata,
            }
            for r in results
        ]
    )
