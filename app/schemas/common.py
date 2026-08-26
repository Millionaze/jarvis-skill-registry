from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base for every request body.

    `extra="forbid"` is a tenancy control, not a style choice: a client that
    tries to smuggle `organization_id` (or any other unmodelled field) into a
    request body gets a 422 instead of having it silently ignored. Tenancy comes
    only from the signed token.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorBody(BaseModel):
    code: str = Field(examples=["SKILL_NOT_FOUND"])
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """The one and only error shape returned by this API."""

    error: ErrorBody
