"""
FastAPI 应用入口 — app factory 模式。

特性:
    - 通过 lifespan 管理 Redis 连接池生命周期
    - 全局 CORS 配置
    - 全局异常处理器
    - 统一 API 响应格式
    - /health 健康检查端点
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.deps import get_redis
from app.core.exceptions import AppException
from app.schemas.common import HealthCheckResponse

logger = structlog.get_logger(__name__)
settings = get_settings()


# ---- Lifespan ----

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理 — 启动时预热连接，关闭时清理。"""
    logger.info("app_starting", app=settings.app.APP_NAME, version=settings.app.APP_VERSION)

    # 预热 Redis 连接
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("redis_connected")
    except Exception:
        logger.warning("redis_unavailable")

    yield

    # 清理资源
    from app.core.llm_client import _llm_client
    if _llm_client:
        await _llm_client.close()

    logger.info("app_stopped")


# ---- App Factory ----

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    is_demo = settings.app.DEBUG or settings.app.USE_MOCK_DB

    app = FastAPI(
        title=settings.app.APP_NAME,
        version=settings.app.APP_VERSION,
        docs_url="/docs" if is_demo else None,
        redoc_url="/redoc" if is_demo else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 无数据库时使用 mock session (模拟 ORM 行为，跨请求共享数据)
    if settings.app.USE_MOCK_DB:
        import uuid as _uuid
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock, MagicMock

        from app.core.deps import get_db

        # 模块级共享存储 — 保证多个请求之间数据一致
        _store: dict[str, dict] = {}       # table_name -> {id: instance}
        _store["_id_counter"] = {}

        def _next_id(prefix: str = "") -> str:
            key = prefix or "default"
            n = _store["_id_counter"].get(key, 0) + 1
            _store["_id_counter"][key] = n
            return f"{prefix}-{n:06d}"

        def _make_mock_result(rows: list, scalar_val=0):
            """构建 execute() 返回的 mock 结果对象。"""
            result = MagicMock()
            result.scalars.return_value.all.return_value = rows
            result.scalar.return_value = scalar_val
            result.fetchall.return_value = rows
            return result

        def _mock_get_db():
            """模拟 AsyncSession — 所有请求共享 _store。"""
            mock_session = MagicMock()
            # 当前请求待 flush 的实例
            _pending: list = []

            def _mock_add(instance):
                _pending.append(instance)

            def _mock_delete(instance):
                table = instance.__class__.__tablename__
                if table in _store and instance.id in _store[table]:
                    del _store[table][instance.id]

            async def _mock_flush():
                now = datetime.now(timezone.utc)
                for inst in _pending:
                    table = inst.__class__.__tablename__
                    if not getattr(inst, "id", None):
                        inst.id = _uuid.uuid4()
                    if hasattr(inst, "status") and not inst.status:
                        inst.status = "created"
                    if hasattr(inst, "current_question_index"):
                        inst.current_question_index = inst.current_question_index or 0
                    if hasattr(inst, "order_index") and not inst.order_index:
                        inst.order_index = 0
                    if hasattr(inst, "created_at") and not inst.created_at:
                        inst.created_at = now
                    if hasattr(inst, "updated_at") and not inst.updated_at:
                        inst.updated_at = now
                    # 保存到共享存储
                    _store.setdefault(table, {})[inst.id] = inst
                _pending.clear()

            async def _mock_execute(stmt, params=None):
                """模拟 SQL 执行，支持向量搜索、关系查询等。"""
                sql = str(stmt) if hasattr(stmt, '__str__') else stmt
                rows = []
                qb_items = list(_store.get("question_bank", {}).values())
                interview_items = list(_store.get("interview_sessions", {}).values())
                resume_items = list(_store.get("resumes", {}).values())
                iq_items = list(_store.get("interview_questions", {}).values())

                # 向量搜索 — 基于关键词做模拟评分
                if "question_bank" in sql.lower():
                    # 从检索 query 中提取关键词
                    query_keywords = set()
                    if params:
                        cat = params.get("category", "")
                        diff = params.get("difficulty", "")
                        qtype = params.get("question_type", "")
                        query_keywords = {k.lower() for k in [cat, diff, qtype] if k}
                    rows = []
                    for item in qb_items:
                        tags = [t.lower() for t in (getattr(item, 'tags', []) or [])]
                        category = (getattr(item, 'category', '') or '').lower()
                        item_qtype = (getattr(item, 'question_type', '') or '').lower()
                        difficulty = (getattr(item, 'difficulty', '') or '').lower()
                        content = (getattr(item, 'content', '') or '').lower()

                        # 关键词匹配越多相似度越高
                        score = 0.05  # 基础分很低
                        key_terms = {category, item_qtype, difficulty}
                        for kw in query_keywords:
                            if kw in key_terms:
                                score += 0.25
                            if any(kw in t for t in tags):
                                score += 0.08
                            if kw in content:
                                score += 0.02
                        score = min(score, 0.95)

                        row = MagicMock()
                        row.id = item.id; row.content = item.content; row.similarity = round(score, 4)
                        row.category = category; row.difficulty = difficulty; row.question_type = item_qtype
                        row.tags = tags; row.reference_answer = getattr(item, 'reference_answer', None)
                        row.key_points = getattr(item, 'key_points', [])
                        rows.append(row)

                    # 按相似度降序排列，取 top_k
                    top_k = params.get("top_k", 5) if params else 5
                    rows.sort(key=lambda r: r.similarity, reverse=True)
                    rows = rows[:top_k]
                    return _make_mock_result(rows, scalar_val=len(rows))

                # Query-specific tables
                if "interview_questions" in sql.lower():
                    return _make_mock_result(iq_items, scalar_val=len(iq_items))
                if "interview_sessions" in sql.lower():
                    return _make_mock_result(interview_items, scalar_val=len(interview_items))
                if "resumes" in sql.lower():
                    return _make_mock_result(resume_items, scalar_val=len(resume_items))

                all_rows = qb_items + interview_items + resume_items + iq_items
                return _make_mock_result(all_rows, scalar_val=len(all_rows))

            async def _mock_get(model_cls, obj_id):
                table = model_cls.__tablename__
                return _store.get(table, {}).get(obj_id)

            async def _mock_refresh(instance):
                pass

            mock_session.add = _mock_add
            mock_session.delete = _mock_delete
            mock_session.flush = _mock_flush
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session.close = AsyncMock()
            mock_session.execute = _mock_execute
            mock_session.get = _mock_get
            mock_session.refresh = _mock_refresh

            return mock_session

        app.dependency_overrides[get_db] = _mock_get_db
        logger.info("demo_mode_enabled", note="内存存储已启用，跨请求数据共享")

    # 静态文件
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 注册路由
    app.include_router(api_router, prefix=settings.app.API_V1_PREFIX)

    # 前端首页
    @app.get("/", include_in_schema=False)
    async def index():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "AI Mock Interview API", "docs": "/docs"}

    # 健康检查
    @app.get("/health", response_model=HealthCheckResponse, tags=["health"])
    async def health_check():
        return HealthCheckResponse(
            status="healthy",
            version=settings.app.APP_VERSION,
            services={"api": "ok"},
        )

    # 全局异常处理器
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", error=str(exc), path=str(request.url))
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "Internal server error",
                "detail": {},
            },
        )

    return app


# ---- WSGI / ASGI 入口 ----
app = create_app()
