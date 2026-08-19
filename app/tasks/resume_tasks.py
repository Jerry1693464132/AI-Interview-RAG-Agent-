"""
简历异步任务 — 简历解析 + 候选人画像提取。

任务:
    parse_and_extract — 上传后自动：解析简历 → 提取画像
"""

from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="resume:parse_and_extract", max_retries=2, default_retry_delay=60, soft_time_limit=180)
def parse_and_extract(self, resume_id: str, file_path: str) -> dict:
    """
    解析简历并提取候选人画像。

    Args:
        resume_id: 简历记录 ID
        file_path: 上传文件路径

    Returns:
        {"resume_id": "...", "status": "completed", "profile_id": "..."}
    """
    import asyncio

    async def _run():
        from app.core.database import async_session_factory
        from app.core.llm_client import get_llm_client
        from app.models.resume import CandidateProfile, Resume, ResumeStatus
        from app.services.profile_extractor import ProfileExtractor
        from app.services.resume_parser import ResumeParser

        async with async_session_factory() as db:
            resume = await db.get(Resume, resume_id)
            if not resume:
                return {"error": "Resume not found"}

            try:
                resume.status = ResumeStatus.PROCESSING
                await db.commit()

                llm = get_llm_client()

                # Step 1: 解析 PDF
                parser = ResumeParser(llm)
                structured = await parser.parse(file_path)
                resume.structured_data = structured
                resume.raw_text = structured.get("raw_text", str(structured))

                # Step 2: 提取画像
                extractor = ProfileExtractor(llm)
                profile_data = await extractor.extract(structured)

                profile = CandidateProfile(
                    resume_id=resume.id,
                    name=profile_data.get("name"),
                    email=profile_data.get("email"),
                    phone=profile_data.get("phone"),
                    skills=profile_data.get("skills", []),
                    skill_levels={s["skill"]: s["level"] for s in profile_data.get("core_skills", [])},
                    years_of_experience=profile_data.get("years_of_experience") or 0,
                    education_summary=profile_data.get("education_summary"),
                    work_summary=profile_data.get("work_summary"),
                    target_role=profile_data.get("target_role"),
                    target_industry=profile_data.get("target_industry"),
                    target_level=profile_data.get("target_level"),
                    analysis_result=profile_data,
                )
                db.add(profile)
                resume.status = ResumeStatus.COMPLETED
                await db.commit()

                logger.info("resume_parsed_and_profiled", resume_id=resume_id, profile_id=str(profile.id))
                return {"resume_id": resume_id, "status": "completed", "profile_id": str(profile.id)}

            except Exception as exc:
                resume.status = ResumeStatus.FAILED
                resume.error_message = str(exc)
                await db.commit()
                logger.error("resume_parse_failed", resume_id=resume_id, error=str(exc))
                raise

    return asyncio.run(_run())
