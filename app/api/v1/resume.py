"""
简历模块 API — 上传、解析、画像提取。

API:
    POST   /resumes/upload           — 上传简历（触发异步解析+画像提取）
    POST   /resumes/upload-sync      — 上传并同步解析（直接返回画像用于出题）
    GET    /resumes/                 — 简历列表
    GET    /resumes/{id}             — 简历详情
    GET    /resumes/{id}/profile     — 候选人画像
    DELETE /resumes/{id}             — 删除简历
"""

import shutil
import uuid as _uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.llm_client import get_llm_client
from app.models.resume import CandidateProfile, Resume, ResumeStatus
from app.schemas.common import APIResponse
from app.schemas.resume import (
    ProfileResponse,
    ResumeDetailResponse,
    ResumeListResponse,
    ResumeUploadResponse,
)

router = APIRouter()
settings = get_settings()

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.get("/", response_model=APIResponse[list[ResumeListResponse]])
async def list_resumes(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """列出已上传的简历。"""
    stmt = select(Resume).order_by(Resume.created_at.desc())
    if status:
        stmt = stmt.where(Resume.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return APIResponse(data=[ResumeListResponse(id=r.id, original_filename=r.original_filename, status=r.status, created_at=r.created_at) for r in result.scalars().all()])


@router.post("/upload", response_model=APIResponse[ResumeUploadResponse])
async def upload_resume(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """上传简历文件，触发异步解析+画像提取。"""
    if not file.filename:
        return APIResponse(code=400, message="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt", ".md"):
        return APIResponse(code=400, message=f"不支持的文件类型: {suffix}")

    file_id = _uuid.uuid4()
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    resume = Resume(original_filename=file.filename, file_path=str(dest), file_type=suffix.lstrip("."), status=ResumeStatus.PENDING)
    db.add(resume)
    await db.flush()
    await db.refresh(resume)

    # 触发异步解析
    from app.tasks.resume_tasks import parse_and_extract
    parse_and_extract.delay(str(resume.id), str(dest))

    return APIResponse(data=ResumeUploadResponse(id=resume.id, original_filename=resume.original_filename, status=resume.status))


@router.post("/upload-sync", response_model=APIResponse[dict])
async def upload_and_parse_sync(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """上传简历并同步解析，直接返回画像数据。"""
    if not file.filename:
        return APIResponse(code=400, message="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    file_id = _uuid.uuid4()
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 保存
    resume = Resume(original_filename=file.filename, file_path=str(dest), file_type=suffix.lstrip("."), status=ResumeStatus.PROCESSING)
    db.add(resume)
    await db.flush()

    try:
        llm = get_llm_client()
        from app.services.resume_parser import ResumeParser
        from app.services.profile_extractor import ProfileExtractor

        parser = ResumeParser(llm)
        structured = await parser.parse(str(dest))
        resume.structured_data = structured
        resume.raw_text = str(structured)
        resume.status = ResumeStatus.COMPLETED

        extractor = ProfileExtractor(llm)
        profile_data = await extractor.extract(structured)

        profile = CandidateProfile(
            resume_id=resume.id, name=profile_data.get("name"),
            email=profile_data.get("email"), phone=profile_data.get("phone"),
            skills=profile_data.get("skills", []),
            skill_levels={s["skill"]: s["level"] for s in profile_data.get("core_skills", [])},
            years_of_experience=0,
            education_summary=profile_data.get("education_summary"),
            work_summary=profile_data.get("work_summary"),
            target_role=profile_data.get("target_role"),
            target_industry=profile_data.get("target_industry", ""),
            target_level=profile_data.get("target_level"),
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        return APIResponse(data={
            "resume_id": str(resume.id),
            "profile_id": str(profile.id),
            "core_skills": profile_data.get("core_skills", []),
            "strengths": profile_data.get("strengths", []),
            "risk_areas": profile_data.get("risk_areas", []),
            "analysis_summary": profile_data.get("analysis_summary", ""),
            "interview_strategy": profile_data.get("interview_strategy", ""),
            "target_role": profile_data.get("target_role", ""),
            "target_level": profile_data.get("target_level", ""),
            "education_summary": profile_data.get("education_summary", {}),
            "work_summary": profile_data.get("work_summary", {}),
        })
    except Exception as exc:
        resume.status = ResumeStatus.FAILED
        resume.error_message = str(exc)
        await db.commit()
        return APIResponse(code=500, message=f"解析失败: {exc}")


@router.get("/{resume_id}", response_model=APIResponse[ResumeDetailResponse])
async def get_resume(resume_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取简历详情。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise NotFoundError("Resume", resume_id)
    return APIResponse(data=ResumeDetailResponse(
        id=resume.id, original_filename=resume.original_filename, status=resume.status,
        file_type=resume.file_type, raw_text=resume.raw_text, structured_data=resume.structured_data,
        profile=None, created_at=resume.created_at, updated_at=resume.updated_at,
    ))


@router.get("/{resume_id}/profile", response_model=APIResponse[ProfileResponse])
async def get_resume_profile(resume_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取候选人画像。"""
    resume = await db.get(Resume, resume_id)
    if not resume or not resume.profile:
        raise NotFoundError("CandidateProfile", resume_id)
    p = resume.profile
    return APIResponse(data=ProfileResponse(
        id=p.id, name=p.name,
        core_skills=[{"skill": s, "level": p.skill_levels.get(s, "intermediate"), "years": 0, "evidence": ""} for s in (p.skills or [])],
        strengths=[], risk_areas=[],
        analysis_summary=f"候选人 {p.name or '未知'}，目标{p.target_role or '未知'}，{p.years_of_experience or 0}年经验",
        interview_strategy="",
        target_role=p.target_role or "", target_level=p.target_level or "",
        education_summary=p.education_summary, work_summary=p.work_summary,
    ))


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(resume_id: UUID, db: AsyncSession = Depends(get_db)):
    """删除简历。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise NotFoundError("Resume", resume_id)
    await db.delete(resume)
    await db.commit()
