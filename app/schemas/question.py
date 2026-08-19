"""题目相关 Schema。"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionSearchRequest(BaseModel):
    """题目检索请求。"""

    query: str = Field(..., min_length=1)
    category: Optional[str] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)


class QuestionSearchResult(BaseModel):
    """题目检索结果（单条）。"""

    id: UUID
    content: str
    score: float
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    metadata: dict
