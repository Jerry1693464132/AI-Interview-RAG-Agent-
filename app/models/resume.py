"""
简历与候选人画像模型。

Resume         — 原始简历 + AI 解析结果
CandidateProfile— 候选人画像（技能、经验、目标岗位）
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.interview import InterviewSession


class ResumeStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Resume(Base, UUIDMixin, TimestampMixin):
    """简历 — 原始上传 + AI 结构化解析结果。"""

    __tablename__ = "resumes"

    # 文件信息
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf, docx, txt

    # 解析状态
    status: Mapped[str] = mapped_column(
        String(20), default=ResumeStatus.PENDING, nullable=False, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI 解析结果（JSONB 灵活存储）
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    """
    structured_data 结构:
    {
        "personal_info": {
            "name": "张三",
            "email": "...",
            "phone": "...",
            "location": "北京"
        },
        "education": [
            {"school": "清华大学", "degree": "硕士", "major": "计算机科学", "year": "2020-2023"}
        ],
        "experience": [
            {
                "company": "字节跳动",
                "title": "高级后端工程师",
                "duration": "2020.06 - 2023.06",
                "description": "负责...",
                "skills_used": ["Python", "Go", "Kubernetes"]
            }
        ],
        "projects": [...],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", ...],
        "certifications": [...]
    }
    """

    # 关联 — 候选人画像
    profile: Mapped[Optional["CandidateProfile"]] = relationship(
        "CandidateProfile", back_populates="resume", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Resume(id={self.id}, file={self.original_filename}, status={self.status})>"


class CandidateProfile(Base, UUIDMixin, TimestampMixin):
    """候选人画像 — 从简历中提取的结构化能力模型。"""

    __tablename__ = "candidate_profiles"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # 基本信息
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # 技能画像
    skills: Mapped[list] = mapped_column(JSONB, default=list)
    """标准化技能列表: ["Python", "FastAPI", "PostgreSQL", "Redis"]"""

    skill_levels: Mapped[dict] = mapped_column(JSONB, default=dict)
    """技能熟练度: {"Python": "expert", "Go": "intermediate"}"""

    years_of_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 教育背景（JSONB）
    education_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    """
    {
        "highest_degree": "硕士",
        "top_schools": ["清华大学"],
        "major_fields": ["计算机科学"]
    }
    """

    # 工作履历摘要
    work_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    """
    {
        "total_companies": 3,
        "latest_title": "高级后端工程师",
        "industry_domains": ["互联网", "金融科技"],
        "typical_tenure_months": 24
    }
    """

    # 目标岗位
    target_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # junior/mid/senior/staff

    # AI 深度分析完整结果（core_skills/strengths/risk_areas/analysis_summary/interview_strategy）
    analysis_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 关联
    resume: Mapped["Resume"] = relationship("Resume", back_populates="profile")

    def __repr__(self) -> str:
        return f"<CandidateProfile(name={self.name}, target_role={self.target_role})>"
