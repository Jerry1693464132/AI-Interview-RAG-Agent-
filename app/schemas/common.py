"""
通用 Schema — 统一响应封装。

约定:
    - 成功:  { "code": 200, "message": "ok", "data": ... }
"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一成功响应。"""

    code: int = Field(default=200, description="HTTP 状态码")
    message: str = Field(default="ok", description="状态描述")
    data: Optional[T] = Field(default=None, description="响应数据")

    model_config = {"from_attributes": True}


class HealthCheckResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(default="healthy")
    version: str
    services: dict[str, str] = Field(default_factory=dict)
