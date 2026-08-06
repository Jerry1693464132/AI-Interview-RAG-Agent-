"""
API 层依赖注入 — 从 core.deps 重新导出，方便路由使用。

Usage:
    from app.api.deps import get_db, get_llm_client, get_redis
"""

from app.core.deps import get_db, get_llm_client, get_redis

__all__ = ["get_db", "get_llm_client", "get_redis"]
