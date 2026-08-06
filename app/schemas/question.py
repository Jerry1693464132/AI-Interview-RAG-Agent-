"""题目相关 Schema。"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionResponse(BaseModel):
    """题目响应。"""

    id: UUID
    content: str
    question_type: str
    difficulty: str
    order_index: int
    reference_answer: Optional[str] = None
    key_points: list[str] = Field(default_factory=list)
    score: Optional[float] = None


class QuestionSearchRequest(BaseModel):
    """题目检索请求。"""

    query: str = Field(..., min_length=1)
    category: Optional[str] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)


class QuestionBankCreateRequest(BaseModel):
    """题库新增请求。"""

    content: str = Field(..., min_length=1)
    category: str = Field(default="general")
    subcategory: Optional[str] = None
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    question_type: str = Field(default="technical")
    tags: list[str] = Field(default_factory=list)
    reference_answer: Optional[str] = None
    key_points: list[str] = Field(default_factory=list)
    source: Optional[str] = None
