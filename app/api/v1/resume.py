"""
简历模块 API — 上传并同步解析。

API:
    POST   /resumes/upload-sync      — 上传简历并同步解析（直接返回画像用于出题）
"""

import shutil
import uuid as _uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.config import get_settings
from app.core.llm_client import get_llm_client
from app.models.resume import CandidateProfile, Resume, ResumeStatus
from app.schemas.common import APIResponse

router = APIRouter()
settings = get_settings()

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


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
