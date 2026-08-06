"""面试会话模型。"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.question import InterviewQuestion


class InterviewStatus:
    CREATED = "created"
    MATCHING = "matching"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class InterviewSession(Base, UUIDMixin, TimestampMixin):
    """模拟面试会话。"""

    __tablename__ = "interview_sessions"

    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    job_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resume_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="SET NULL"), nullable=True
    )

    question_count: Mapped[int] = mapped_column(Integer, default=5)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    question_types: Mapped[list] = mapped_column(JSONB, default=list)

    match_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=InterviewStatus.CREATED, nullable=False, index=True)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    questions: Mapped[list["InterviewQuestion"]] = relationship(
        "InterviewQuestion", back_populates="session", cascade="all, delete-orphan",
        order_by="InterviewQuestion.order_index"
    )

    def __repr__(self) -> str:
        return f"<InterviewSession(job={self.job_title}, status={self.status})>"
