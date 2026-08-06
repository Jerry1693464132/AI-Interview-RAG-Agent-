"""API 集成测试。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_api_v1_routes(async_client: AsyncClient):
    endpoints = [
        "/api/v1/resumes/",
        "/api/v1/interviews/",
        "/api/v1/questions/",
    ]
    for endpoint in endpoints:
        response = await async_client.get(endpoint)
        assert response.status_code == 200, f"{endpoint} returned {response.status_code}"


@pytest.mark.asyncio
async def test_404(async_client: AsyncClient):
    response = await async_client.get("/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_openapi_schema(async_client: AsyncClient):
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    assert "/health" in paths
    assert "/api/v1/resumes/" in paths
    assert "/api/v1/resumes/{resume_id}" in paths
    assert "/api/v1/resumes/{resume_id}/profile" in paths
    assert "/api/v1/interviews/" in paths
    assert "/api/v1/interviews/{interview_id}" in paths
    assert "/api/v1/interviews/{interview_id}/generate-questions" in paths
    assert "/api/v1/interviews/{interview_id}/questions" in paths
    assert "/api/v1/questions/" in paths
    assert "/api/v1/questions/search" in paths
    assert "/api/v1/questions/{question_id}" in paths
