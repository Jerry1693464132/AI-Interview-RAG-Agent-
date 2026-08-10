"""题目相关 Schema。"""

from typing import Optional

from pydantic import BaseModel, Field


class QuestionSearchRequest(BaseModel):
    """题目检索请求。"""

    query: str = Field(..., min_length=1)
    category: Optional[str] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)
