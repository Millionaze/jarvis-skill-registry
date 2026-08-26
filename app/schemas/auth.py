from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import StrictModel


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    # Suppressing S105 here: the RFC 6750 token *type*, not a token value.
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    organization_id: uuid.UUID


__all__ = ["CurrentUserResponse", "EmailStr", "LoginRequest", "TokenResponse"]
