"""
统一异常体系 — 项目所有自定义异常。

层次结构:
    AppException         (基础)
    ├── NotFoundError    (404)
    ├── ValidationError  (422)
    ├── UnauthorizedError(401)
    ├── ForbiddenError   (403)
    └── LLMError         (502 — LLM 调用失败)
"""

from typing import Any, Optional


class AppException(Exception):
    """应用异常基类。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(AppException):
    """资源未找到 (404)。"""

    def __init__(self, resource: str, resource_id: Any) -> None:
        super().__init__(
            message=f"{resource} not found: {resource_id}",
            status_code=404,
            detail={"resource": resource, "id": str(resource_id)},
        )


class ValidationError(AppException):
    """请求参数校验失败 (422)。"""

    def __init__(self, message: str, *, detail: Optional[dict] = None) -> None:
        super().__init__(message=message, status_code=422, detail=detail)


class UnauthorizedError(AppException):
    """未认证 (401)。"""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message=message, status_code=401)


class ForbiddenError(AppException):
    """无权限 (403)。"""

    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message=message, status_code=403)


class LLMError(AppException):
    """LLM 调用失败 (502)。"""

    def __init__(self, message: str, *, detail: Optional[dict] = None) -> None:
        super().__init__(message=message, status_code=502, detail=detail)
