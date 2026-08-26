from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.errors import AuthenticationError, ErrorCode
from app.core.security import create_access_token, verify_password
from app.db.repository import UnscopedAuthRepository
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a token")
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    """The token carries the organization claim that scopes every later request."""
    user = await UnscopedAuthRepository(session).get_user_by_email(payload.email)

    # Same error and roughly the same work whether the user exists or not.
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise AuthenticationError(
            "Email or password is incorrect.", code=ErrorCode.INVALID_CREDENTIALS
        )

    settings = get_settings()
    token = create_access_token(
        user_id=user.id, organization_id=user.organization_id, role=user.role
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_minutes * 60)


@router.get("/me", response_model=CurrentUserResponse, summary="Who am I, and for which org")
async def me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)
