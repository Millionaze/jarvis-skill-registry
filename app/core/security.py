"""Self-contained authentication primitives: bcrypt hashing and HS256 tokens.

Scoped for this evaluation. In production this whole module is replaced by the
platform identity provider (see ARCHITECTURE.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ErrorCode

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(*, user_id: uuid.UUID, organization_id: uuid.UUID, role: str) -> str:
    """Mint an access token.

    The organization is a signed claim. It is the ONLY source of tenancy for a
    request - never a body field, query parameter or path segment.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed
        raise AuthenticationError(
            "Access token is invalid or has expired.", code=ErrorCode.INVALID_TOKEN
        ) from exc

    if not claims.get("sub") or not claims.get("org"):
        raise AuthenticationError(
            "Access token is missing required claims.", code=ErrorCode.INVALID_TOKEN
        )
    return claims
