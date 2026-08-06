"""面试相关 Schema。"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InterviewCreateRequest(BaseModel):
    """创建面试请求。"""

    resume_id: Optional[UUID] = None
    job_title: str = Field(..., min_length=1, max_length=200)
    job_description: Optional[str] = None
    question_count: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    question_types: list[str] = Field(default_factory=lambda: ["technical", "behavioral"])


class InterviewSessionResponse(BaseModel):
    """面试会话响应。"""

    id: UUID
    job_title: str
    status: str
    question_count: int
    difficulty: str
    match_result: Optional[dict] = None
    current_question_index: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
