from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    status_code: int = 500
    code: str = "unknown_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.detail = detail


class InvalidUrl(ApiError):
    status_code = 400
    code = "invalid_url"


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class CreatorNotFound(NotFound):
    code = "creator_not_found"


class TaskNotFound(NotFound):
    code = "task_not_found"


class AlreadyProcessed(ApiError):
    status_code = 409
    code = "already_processed"


class CookieMissing(ApiError):
    status_code = 403
    code = "cookie_missing"


class CookieInvalid(ApiError):
    status_code = 403
    code = "cookie_invalid"


class InvalidCookieFile(ApiError):
    status_code = 400
    code = "invalid_cookie_file"


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    payload = {"error": {"code": exc.code, "message": exc.message}}
    if exc.detail is not None:
        payload["error"]["detail"] = exc.detail
    return JSONResponse(payload, status_code=exc.status_code)
