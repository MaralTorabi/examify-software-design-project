"""HTTP translation for application and request errors."""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExamifyError,
    InsufficientSourceContentError,
    InvalidExamTransitionError,
    NotFoundError,
    ValidationError,
    format_error_envelope,
)

logger = logging.getLogger(__name__)


class UploadTooLargeError(ExamifyError):
    default_code = "UPLOAD_TOO_LARGE"


class UnsupportedFileError(ExamifyError):
    default_code = "UNSUPPORTED_FILE_TYPE"


STATUS = {
    AuthenticationError: 401,
    AuthorizationError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    InvalidExamTransitionError: 409,
    UploadTooLargeError: 413,
    UnsupportedFileError: 415,
    ValidationError: 422,
    InsufficientSourceContentError: 422,
}


def error_response(request, status, code, message, headers=None):
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status,
        content=format_error_envelope(code, message, request_id),
        headers={**(headers or {}), "X-Request-ID": request_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ExamifyError)
    async def application_error(request: Request, exc: ExamifyError):
        status = next((value for kind, value in STATUS.items() if isinstance(exc, kind)), 500)
        if status == 500:
            logger.error("Unhandled application error for request %s", request.state.request_id)
            return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return error_response(request, status, exc.code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError):
        message = "Invalid request."
        if exc.errors():
            detail = exc.errors()[0]
            field = ".".join(map(str, detail["loc"]))
            message = f"{field}: invalid or missing value."
        return error_response(request, 422, "VALIDATION_FAILED", message)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(
            request, exc.status_code, f"HTTP_{exc.status_code}", exc.detail, exc.headers
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled %s for request %s", type(exc).__name__, request.state.request_id)
        return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
