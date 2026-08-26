"""Domain errors and the single error envelope used by every response.

Every failure the client can see is shaped as::

    {"error": {"code": "SKILL_NOT_FOUND", "message": "...", "detail": {...}}}

`code` is the machine-readable contract; `message` is for humans; `detail` is
optional structured context. Stack traces never reach the client.
"""

from __future__ import annotations

from typing import Any


class ErrorCode:
    """Machine-readable error codes. Referenced by tests and by clients."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    # Suppressing S105 here: an error code, not a credential - the value is its own name.
    INVALID_TOKEN = "INVALID_TOKEN"  # noqa: S105

    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
    SKILL_VERSION_NOT_FOUND = "SKILL_VERSION_NOT_FOUND"
    SKILL_NAME_CONFLICT = "SKILL_NAME_CONFLICT"
    SKILL_DISABLED = "SKILL_DISABLED"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"

    NOT_ORG_OWNER = "NOT_ORG_OWNER"

    VERSION_NOT_REVIEWED = "VERSION_NOT_REVIEWED"
    VERSION_NOT_ACTIVATABLE = "VERSION_NOT_ACTIVATABLE"
    VERSION_ALREADY_REVIEWED = "VERSION_ALREADY_REVIEWED"
    ACTIVE_VERSION_IMMUTABLE = "ACTIVE_VERSION_IMMUTABLE"

    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    FORBIDDEN_TOOL_PATTERN = "FORBIDDEN_TOOL_PATTERN"
    TOOL_NOT_REQUESTED = "TOOL_NOT_REQUESTED"

    VALIDATION_ERROR = "VALIDATION_ERROR"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DomainError(Exception):
    """Base class for every error that maps onto an HTTP response."""

    status_code: int = 400
    code: str = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.detail: dict[str, Any] = detail or {}

    def envelope(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "detail": self.detail}}


class AuthenticationError(DomainError):
    status_code = 401
    code = ErrorCode.INVALID_CREDENTIALS


class PermissionDeniedError(DomainError):
    """403. Only ever raised once the caller has been shown to own the resource.

    Cross-tenant access never reaches this class - it raises ResourceNotFound so
    that a 403 can never confirm the existence of another tenant's row.
    """

    status_code = 403
    code = ErrorCode.NOT_ORG_OWNER


class ResourceNotFoundError(DomainError):
    status_code = 404
    code = ErrorCode.NOT_FOUND


class ConflictError(DomainError):
    status_code = 409


class UnprocessableError(DomainError):
    status_code = 422


class ImmutableVersionError(Exception):
    """Raised by the SQLAlchemy before_update guard (application defence layer).

    Not a DomainError: it signals a programming mistake reaching the ORM, and is
    translated to a 409 ACTIVE_VERSION_IMMUTABLE at the edge.
    """
