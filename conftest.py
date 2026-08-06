"""
Pytest 全局 fixtures — 为所有测试提供共享的测试工具。

提供的 fixtures:
    - async_client   AsyncClient (httpx) — 用于 FastAPI 路由集成测试
    - test_settings  Settings — 测试用配置

注意:
    - 测试环境不依赖真实数据库，通过 FastAPI dependency_overrides 注入 mock
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.main import create_app


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """测试环境配置。"""
    return get_settings()


def _override_get_db() -> AsyncSession:
    """测试用 DB session mock — 返回一个带 AsyncMock 的 session。"""
    # execute() 的结果需要支持 .scalars().all() 和 .scalar() 链式调用
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0
    mock_result.fetchall.return_value = []

    mock_session = MagicMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.get = AsyncMock(return_value=None)
    mock_session.add = MagicMock()
    mock_session.delete = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.close = AsyncMock()
    return mock_session


@pytest.fixture
async def async_client() -> AsyncClient:
    """
    异步 HTTP 测试客户端 — 不启动真实服务器，使用 ASGI transport。

    自动覆盖 get_db 依赖，避免测试需要真实数据库。
    """
    app = create_app()

    # 覆盖数据库依赖 — 使用 mock session
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
