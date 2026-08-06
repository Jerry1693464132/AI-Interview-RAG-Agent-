"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import interview, questions, resume

api_router = APIRouter()

api_router.include_router(resume.router, prefix="/resumes", tags=["Resume"])
api_router.include_router(interview.router, prefix="/interviews", tags=["Interview"])
api_router.include_router(questions.router, prefix="/questions", tags=["Questions"])
