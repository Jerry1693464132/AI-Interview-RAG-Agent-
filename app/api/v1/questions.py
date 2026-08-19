"""
题库检索 API。

API:
    POST   /questions/search        — 语义检索（RAG）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.rag.embeddings import get_embedding_client
from app.rag.vector_store import VectorStore
from app.schemas.common import APIResponse
from app.schemas.question import QuestionSearchRequest, QuestionSearchResult

router = APIRouter()


@router.post("/search", response_model=APIResponse[list[QuestionSearchResult]])
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
