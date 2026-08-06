"""
题目模型。

InterviewQuestion — 面试中生成的题目（含参考答案和得分点）
QuestionBank     — 题库（含 embedding 向量，用于 RAG 检索）
"""

import uuid
from typing import TYPE_CHECKING, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.interview import InterviewSession


class InterviewQuestion(Base, UUIDMixin, TimestampMixin):
    """面试题目 — AI 生成的个性化面试题。"""

    __tablename__ = "interview_questions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    reference_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_points: Mapped[list] = mapped_column(JSONB, default=list)

    source_chunks: Mapped[list] = mapped_column(JSONB, default=list)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    session: Mapped["InterviewSession"] = relationship("InterviewSession", back_populates="questions")

    def __repr__(self) -> str:
        return f"<InterviewQuestion(type={self.question_type}, order={self.order_index})>"


class QuestionBank(Base, UUIDMixin, TimestampMixin):
    """题库 — 预置题目，支持向量语义检索。"""

    __tablename__ = "question_bank"

    # 题目内容
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 分类标签
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    """大类: backend / frontend / data / devops / product"""
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    """小类: python / golang / react / machine_learning"""
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    """标签: ["Python", "Django", "ORM"]"""

    # 评分依据
    reference_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_points: Mapped[list] = mapped_column(JSONB, default=list)

    # 向量（DashScope text-embedding-v3: 1024 维）
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024), nullable=True)

    # 元数据
    source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<QuestionBank(category={self.category}, type={self.question_type})>"
