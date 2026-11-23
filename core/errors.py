from __future__ import annotations

from typing import Any


class ExamifyError(Exception):
    """Base exception for all Examify domain and application errors."""

    default_code: str = "EXAMIFY_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.context = context or {}

    def to_envelope(self, request_id: str | None = None) -> dict[str, dict[str, Any]]:
        return format_error_envelope(
            code=self.code,
            message=self.message,
            request_id=request_id,
        )


class AuthenticationError(ExamifyError):
    """Raised when authentication fails or credentials are invalid/missing."""

    default_code: str = "AUTHENTICATION_FAILED"


class AuthorizationError(ExamifyError):
    """Raised when the authenticated actor lacks permissions for an action."""

    default_code: str = "PERMISSION_DENIED"


class NotFoundError(ExamifyError):
    """Raised when a requested resource does not exist."""

    default_code: str = "RESOURCE_NOT_FOUND"


class ConflictError(ExamifyError):
    """Raised on state conflicts such as duplicate resources or optimistic lock failures."""

    default_code: str = "STATE_CONFLICT"


class ValidationError(ExamifyError):
    """Raised when payload or domain boundary validation fails."""

    default_code: str = "VALIDATION_FAILED"


class InvalidExamTransitionError(ExamifyError):
    """Raised when attempting an illegal transition in the Exam state machine."""

    default_code: str = "INVALID_EXAM_TRANSITION"


class InsufficientSourceContentError(ExamifyError):
    """Raised when extracted PDF text is insufficient to generate required questions."""

    default_code: str = "INSUFFICIENT_SOURCE_CONTENT"


def format_error_envelope(
    code: str,
    message: str,
    request_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Formats standard JSON error envelope: `{"error": {"code", "message", "request_id"}}`."""
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
