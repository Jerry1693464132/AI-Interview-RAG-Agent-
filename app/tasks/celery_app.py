"""Celery 实例 — 异步任务队列（简历解析等耗时操作）。"""

from celery import Celery
from celery.utils.log import get_task_logger

from app.core.config import get_settings

settings = get_settings()
logger = get_task_logger(__name__)

celery_app = Celery("ai_mock_interview", broker=settings.celery.BROKER_URL, backend=settings.celery.RESULT_BACKEND)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_default_retry_delay=60,
    task_max_retries=3,
    task_time_limit=300,
    task_soft_time_limit=240,
    imports=["app.tasks.resume_tasks"],
)
