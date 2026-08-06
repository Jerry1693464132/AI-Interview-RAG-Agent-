"""
通用 Schema — 统一响应封装、分页、错误格式。

约定:
    - 成功:  { "code": 200, "message": "ok", "data": ... }
    - 分页:  { "code": 200, "message": "ok", "data": [...], "pagination": {...} }
    - 错误:  { "code": 4xx/5xx, "message": "...", "detail": {...} }
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一成功响应。"""

    code: int = Field(default=200, description="HTTP 状态码")
    message: str = Field(default="ok", description="状态描述")
    data: Optional[T] = Field(default=None, description="响应数据")

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    """分页元信息。"""

    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=100, description="每页条数")
    total: int = Field(..., ge=0, description="总数")
    total_pages: int = Field(..., ge=0, description="总页数")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应。"""

    code: int = Field(default=200)
    message: str = Field(default="ok")
    data: list[T] = Field(default_factory=list)
    pagination: PaginationMeta


class ErrorResponse(BaseModel):
    """统一错误响应。"""

    code: int = Field(..., description="HTTP 状态码")
    message: str = Field(..., description="错误消息")
    detail: Optional[dict[str, Any]] = Field(default=None, description="错误详情")


class HealthCheckResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(default="healthy")
    version: str
    services: dict[str, str] = Field(default_factory=dict)
