"""
面试流程 API — 创建面试 + 基于简历画像出题。

API:
    POST   /interviews/                         — 创建面试
    GET    /interviews/                         — 面试列表
    GET    /interviews/{id}                     — 面试详情
    POST   /interviews/{id}/generate-questions  — 基于画像出题
    GET    /interviews/{id}/questions           — 查看题目
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.core.llm_client import get_llm_client
from app.models.interview import InterviewSession, InterviewStatus
from app.models.question import InterviewQuestion
from app.schemas.common import APIResponse
from app.schemas.interview import InterviewCreateRequest, InterviewSessionResponse

router = APIRouter()

_QUESTION_SYSTEM_PROMPT = """你是一位资深技术面试官。根据候选人画像和岗位需求，生成针对性面试题目。

## 要求
- 以 JSON 格式输出: {"questions": [...]}
- 每道题包含:
  - content: 题目内容
  - question_type: 题型 (technical/coding/system_design/behavioral/scenario)
  - reference_answer: 参考答案（详细准确，作为面试官参考）
  - key_points: 关键考查点列表（3-7 个具体可量化的点）

## 出题原则
1. 题目必须针对候选人的实际技能和经验水平
2. reference_answer 必须专业准确
3. key_points 要具体，面试官可据此评判
4. 难度与候选人级别匹配
5. 优先考查候选人简历中声称的核心技能"""


def _build_question_prompt(session: InterviewSession) -> str:
    prompt = (
        f"岗位: {session.job_title}\n"
        f"描述: {session.job_description or '未提供'}\n"
        f"难度: {session.difficulty}\n"
        f"数量: {session.question_count}\n"
        f"类型: {', '.join(session.question_types) if session.question_types else 'technical, behavioral'}\n"
    )
    # 如果有简历画像数据，加入个性化信息
    if session.profile_id:
        prompt += f"\n注意：请基于候选人画像（ID: {session.profile_id}）进行个性化出题。"
    return prompt


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
    # 关联简历画像
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
    """列出面试记录。"""
    from sqlalchemy import select

    stmt = select(InterviewSession).order_by(InterviewSession.created_at.desc())
    if status:
        stmt = stmt.where(InterviewSession.status == status)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return APIResponse(data=[_to_response(s) for s in result.scalars().all()])


@router.get("/{interview_id}", response_model=APIResponse[InterviewSessionResponse])
async def get_interview(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取面试详情。"""
    session = await db.get(InterviewSession, interview_id)
    if not session:
        raise NotFoundError("InterviewSession", interview_id)
    return APIResponse(data=_to_response(session))


# ---- 出题 ----

@router.post("/{interview_id}/generate-questions", response_model=APIResponse[dict])
async def generate_questions(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """使用 DeepSeek 生成个性化面试题目。"""
    session = await db.get(InterviewSession, interview_id)
    if not session:
        raise NotFoundError("InterviewSession", interview_id)

    # 如果有简历画像，获取并注入 Prompt
    profile_context = ""
    if session.profile_id:
        from app.models.resume import CandidateProfile
        profile = await db.get(CandidateProfile, session.profile_id)
        if profile:
            skills = profile.skills or []
            years = profile.years_of_experience or 0
            level = profile.target_level or "mid"
            profile_context = f"\n候选人技能: {', '.join(skills[:15])}\n工作年限: {years} 年\n级别: {level}"

    prompt = _build_question_prompt(session) + profile_context

    llm = get_llm_client()
    import json, re
    response = await llm.chat(
        messages=[
            {"role": "system", "content": _QUESTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or "{}"
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return APIResponse(code=500, message="题目生成失败", data={})

    questions_data = data.get("questions", [])
    generated = []
    for i, q in enumerate(questions_data):
        question = InterviewQuestion(
            session_id=session.id,
            content=q.get("content", ""),
            question_type=q.get("question_type", "technical"),
            difficulty=session.difficulty,
            order_index=i + 1,
            reference_answer=q.get("reference_answer", ""),
            key_points=q.get("key_points", []),
        )
        db.add(question)
        generated.append(question)

    await db.flush()
    session.status = InterviewStatus.IN_PROGRESS
    session.started_at = datetime.now()

    return APIResponse(data={
        "interview_id": str(interview_id),
        "questions": [
            {"id": str(q.id), "content": q.content, "question_type": q.question_type,
             "order_index": q.order_index, "reference_answer": q.reference_answer,
             "key_points": q.key_points}
            for q in generated
        ]
    })


@router.get("/{interview_id}/questions", response_model=APIResponse[list])
async def get_interview_questions(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取面试的所有题目（直接查询，兼容 Mock 模式）。"""
    from sqlalchemy import select
    session = await db.get(InterviewSession, interview_id)
    if not session:
        raise NotFoundError("InterviewSession", interview_id)
    # 直接查询 interview_questions 表，不用 relationship（Mock 模式兼容）
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
