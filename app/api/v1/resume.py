"""
简历模块 API — 上传、异步解析、状态查询。

API:
    POST   /resumes/upload           — 上传简历，触发 Celery 异步解析（秒回）
    GET    /resumes/{resume_id}      — 查询解析状态（前端轮询）
    POST   /resumes/upload-sync      — 上传并同步解析（Mock 模式兜底）
"""

import shutil
import uuid as _uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.llm_client import get_llm_client
from app.models.resume import CandidateProfile, Resume, ResumeStatus
from app.schemas.common import APIResponse

router = APIRouter()
settings = get_settings()

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _profile_payload(profile_data: dict, resume_id: str, profile_id: str) -> dict:
    """组装前端需要的画像响应数据。"""
    return {
        "resume_id": resume_id,
        "profile_id": profile_id,
        "core_skills": profile_data.get("core_skills", []),
        "strengths": profile_data.get("strengths", []),
        "risk_areas": profile_data.get("risk_areas", []),
        "analysis_summary": profile_data.get("analysis_summary", ""),
        "interview_strategy": profile_data.get("interview_strategy", ""),
        "target_role": profile_data.get("target_role", ""),
        "target_level": profile_data.get("target_level", ""),
        "education_summary": profile_data.get("education_summary", {}),
        "work_summary": profile_data.get("work_summary", {}),
    }


@router.post("/upload", response_model=APIResponse[dict])
async def upload_resume(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """上传简历文件，触发 Celery 异步解析（立即返回）。"""
    if not file.filename:
        return APIResponse(code=400, message="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    file_id = _uuid.uuid4()
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    resume = Resume(
        original_filename=file.filename, file_path=str(dest),
        file_type=suffix.lstrip("."), status=ResumeStatus.PENDING,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    # 触发异步解析
    from app.tasks.resume_tasks import parse_and_extract
    parse_and_extract.delay(str(resume.id), str(dest))

    return APIResponse(data={
        "resume_id": str(resume.id),
        "status": resume.status,
    })


@router.get("/{resume_id}", response_model=APIResponse[dict])
async def get_resume_status(resume_id: UUID, db: AsyncSession = Depends(get_db)):
    """查询解析状态 — 前端轮询此端点。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise NotFoundError("Resume", resume_id)

    data: dict = {
        "resume_id": str(resume.id),
        "status": resume.status,
    }
    if resume.error_message:
        data["error_message"] = resume.error_message

    # 解析完成时返回完整画像
    if resume.status == ResumeStatus.COMPLETED:
        from sqlalchemy import select
        result = await db.execute(
            select(CandidateProfile).where(CandidateProfile.resume_id == resume.id)
        )
        profile = result.scalar()
        if profile:
            data["profile_id"] = str(profile.id)
            if profile.analysis_result:
                data.update(profile.analysis_result)

    return APIResponse(data=data)


@router.post("/upload-sync", response_model=APIResponse[dict])
async def upload_and_parse_sync(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """上传简历并同步解析，直接返回画像数据（Mock 模式兜底）。"""
    if not file.filename:
        return APIResponse(code=400, message="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    file_id = _uuid.uuid4()
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    resume = Resume(
        original_filename=file.filename, file_path=str(dest),
        file_type=suffix.lstrip("."), status=ResumeStatus.PROCESSING,
    )
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
            analysis_result=profile_data,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

        return APIResponse(data=_profile_payload(profile_data, str(resume.id), str(profile.id)))
    except Exception as exc:
        resume.status = ResumeStatus.FAILED
        resume.error_message = str(exc)
        await db.commit()
        return APIResponse(code=500, message=f"解析失败: {exc}")
