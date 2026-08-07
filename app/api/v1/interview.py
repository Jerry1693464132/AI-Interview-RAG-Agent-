"""
面试流程 API — 创建面试 + RAG 出题。

API:
    POST   /interviews/                         — 创建面试
    GET    /interviews/                         — 面试列表
    GET    /interviews/{id}                     — 面试详情
    POST   /interviews/{id}/generate-questions  — RAG 出题
    GET    /interviews/{id}/questions           — 查看题目
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.exceptions import NotFoundError
from app.core.llm_client import get_llm_client
from app.models.interview import InterviewSession, InterviewStatus
from app.models.question import InterviewQuestion
from app.schemas.common import APIResponse
from app.schemas.interview import InterviewCreateRequest, InterviewSessionResponse

router = APIRouter()


# ---- 创建面试 ----

@router.post("/", response_model=APIResponse[InterviewSessionResponse], status_code=201)
async def create_interview(
    request: InterviewCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """创建面试会话。"""
    session = InterviewSession(
        job_title=request.job_title,
        job_description=request.job_description,
        question_count=request.question_count,
        difficulty=request.difficulty,
        question_types=request.question_types,
        resume_id=request.resume_id,
    )
    if request.resume_id:
        from app.models.resume import CandidateProfile, Resume
        resume = await db.get(Resume, request.resume_id)
        if resume and resume.profile:
            session.profile_id = resume.profile.id

    db.add(session)
    await db.flush()
    await db.refresh(session)
    return APIResponse(data=_to_response(session))


# ---- 列表 & 详情 ----

@router.get("/", response_model=APIResponse[list[InterviewSessionResponse]])
async def list_interviews(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    stmt = select(InterviewSession).order_by(InterviewSession.created_at.desc())
    if status:
        stmt = stmt.where(InterviewSession.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return APIResponse(data=[_to_response(s) for s in result.scalars().all()])


@router.get("/{interview_id}", response_model=APIResponse[InterviewSessionResponse])
async def get_interview(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(InterviewSession, interview_id)
    if not session:
        raise NotFoundError("InterviewSession", interview_id)
    return APIResponse(data=_to_response(session))


# ---- RAG 出题 ----

@router.post("/{interview_id}/generate-questions", response_model=APIResponse[dict])
async def generate_questions(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """RAG 增强出题：检索题库 → 注入 Prompt → DeepSeek 生成。"""
    session = await db.get(InterviewSession, interview_id)
    if not session:
        raise NotFoundError("InterviewSession", interview_id)

    profile_data: dict = {}
    if session.profile_id:
        from app.models.resume import CandidateProfile
        profile = await db.get(CandidateProfile, session.profile_id)
        if profile:
            profile_data = {
                "skills": profile.skills or [],
                "target_role": profile.target_role or session.job_title,
                "target_level": profile.target_level or "mid",
            }

    from app.rag.embeddings import get_embedding_client
    from app.rag.vector_store import VectorStore
    from app.rag.retriever import HybridRetriever
    from app.services.question_generator import QuestionGenerator

    embedding_client = get_embedding_client()
    retriever = HybridRetriever(VectorStore(db), embedding_client)
    generator = QuestionGenerator(get_llm_client(), retriever)

    questions = await generator.generate(
        session=db,
        interview_id=str(interview_id),
        job_title=session.job_title,
        job_description=session.job_description or "",
        profile=profile_data,
        question_count=session.question_count,
        difficulty=session.difficulty,
        question_types=session.question_types,
    )

    session.status = InterviewStatus.IN_PROGRESS
    session.started_at = datetime.now()

    return APIResponse(data={
        "interview_id": str(interview_id),
        "questions": [
            {"id": str(q.id), "content": q.content, "question_type": q.question_type,
             "order_index": q.order_index, "reference_answer": q.reference_answer,
             "key_points": q.key_points,
             "source": q.source_chunks[0] if q.source_chunks else "unknown"}
            for q in questions
        ]
    })


@router.get("/{interview_id}/questions", response_model=APIResponse[list])
async def get_interview_questions(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    session = await db.get(InterviewSession, interview_id)
    if not session:
        raise NotFoundError("InterviewSession", interview_id)
    result = await db.execute(
        select(InterviewQuestion).where(InterviewQuestion.session_id == interview_id).order_by(InterviewQuestion.order_index)
    )
    questions = result.scalars().all()
    return APIResponse(data=[
        {"id": str(q.id), "content": q.content, "question_type": q.question_type,
         "difficulty": q.difficulty, "order_index": q.order_index,
         "reference_answer": q.reference_answer, "key_points": q.key_points, "score": q.score}
        for q in questions
    ])


def _to_response(s: InterviewSession) -> InterviewSessionResponse:
    return InterviewSessionResponse(
        id=s.id, job_title=s.job_title, status=s.status,
        question_count=s.question_count, difficulty=s.difficulty,
        match_result=s.match_result, current_question_index=s.current_question_index,
        started_at=s.started_at, completed_at=s.completed_at, created_at=s.created_at,
    )
