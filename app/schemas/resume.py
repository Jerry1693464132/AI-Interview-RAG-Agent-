"""简历相关 Schema。"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ResumeUploadResponse(BaseModel):
    id: UUID
    original_filename: str
    status: str


class ResumeDetailResponse(BaseModel):
    id: UUID
    original_filename: str
    status: str
    file_type: str
    raw_text: Optional[str] = None
    structured_data: Optional[dict] = None
    profile: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class ResumeListResponse(BaseModel):
    id: UUID
    original_filename: str
    status: str
    created_at: datetime


class SkillAssessment(BaseModel):
    skill: str
    level: str
    years: int
    evidence: str


class ProfileResponse(BaseModel):
    id: UUID
    name: Optional[str] = None
    core_skills: list[SkillAssessment] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)
    analysis_summary: str = ""
    interview_strategy: str = ""
    target_role: str = ""
    target_level: str = ""
    education_summary: Optional[dict] = None
    work_summary: Optional[dict] = None
