"""Global exception handlers.

Everything a client can see is normalised to::

    {"error": {"code": ..., "message": ..., "detail": {...}}}

Unexpected exceptions are logged server-side and reported as an opaque 500. No
stack trace, driver message or SQL ever crosses the boundary.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import DomainError, ErrorCode, ImmutableVersionError

logger = logging.getLogger("app.errors")

_STATUS_CODES: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.AUTH_REQUIRED,
    status.HTTP_403_FORBIDDEN: ErrorCode.NOT_ORG_OWNER,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCode.VALIDATION_ERROR,
}


def _envelope(code: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(status_code=exc.status_code, content=exc.envelope(), headers=headers)

    @app.exception_handler(ImmutableVersionError)
    async def _immutable_version(_: Request, exc: ImmutableVersionError) -> JSONResponse:
        # The application-layer guard fired. Surface it as a domain conflict.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope(ErrorCode.ACTIVE_VERSION_IMMUTABLE, str(exc)),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        """Safety net: a database constraint did its job, so this is a 409.

        Services translate the violations they expect into specific codes. This
        handler exists so that one they did not anticipate can never reach the
        client as an opaque 500 - a uniqueness race is a conflict, not a bug in
        the server. The driver message is logged, never returned.
        """
        logger.warning("integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope(
                ErrorCode.CONSTRAINT_VIOLATION,
                "The request conflicts with the current state of the resource.",
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "location": list(err.get("loc", [])),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                ErrorCode.VALIDATION_ERROR, "Request failed validation.", {"errors": errors}
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed."
        headers = dict(exc.headers or {})
        return JSONResponse(
            status_code=exc.status_code, content=_envelope(code, message), headers=headers or None
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled error on %s %s", request.method, request.url.path, exc_info=exc
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                ErrorCode.INTERNAL_ERROR, "An unexpected error occurred."
            ),
        )
