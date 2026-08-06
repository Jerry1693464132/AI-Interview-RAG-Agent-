"""
依赖注入 — FastAPI Depends() 可用的共享资源。

提供的依赖:
    get_db          → AsyncSession     (数据库会话)
    get_llm_client  → LLMClient        (DeepSeek 客户端单例)
    get_redis       → redis.Redis      (Redis 连接)
    get_settings    → Settings         (配置单例)
"""

from typing import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import async_session_factory
from app.core.llm_client import LLMClient, get_llm_client


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖: 获取数据库会话。

    请求进入时创建会话，响应返回时自动关闭。
    发生异常时自动回滚。

    Usage:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Redis 连接池（按需创建）
_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    FastAPI 依赖: 获取 Redis 连接。

    使用连接池，无需每次调用都建立新连接。

    Usage:
        @router.get("/cache")
        async def get_cache(redis: aioredis.Redis = Depends(get_redis)):
            value = await redis.get("key")
            ...
    """
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.Redis(
            host=settings.redis.HOST,
            port=settings.redis.PORT,
            password=settings.redis.PASSWORD,
            db=settings.redis.DB,
            decode_responses=True,
        )
    return _redis_pool
