"""统一异常体系。"""

from typing import Any, Optional


class AppException(Exception):
    """应用异常基类。"""

    def __init__(self, message: str, *, status_code: int = 500, detail: Optional[dict[str, Any]] = None) -> None:
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(AppException):
    """资源未找到 (404)。"""

    def __init__(self, resource: str, resource_id: Any) -> None:
        super().__init__(message=f"{resource} not found: {resource_id}", status_code=404, detail={"resource": resource, "id": str(resource_id)})
