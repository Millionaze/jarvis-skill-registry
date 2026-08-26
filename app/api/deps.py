"""Request-scoped dependencies.

`get_current_user` is the ONLY source of tenancy in this application. The
organization is read from a signed token claim and re-validated against the
database; it is never read from a path parameter, query parameter or request
body. Request bodies use `extra="forbid"`, so a client that tries to send
`organization_id` gets a 422 rather than having it quietly ignored.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ErrorCode
from app.db.repository import SkillRepository, UnscopedAuthRepository
from app.db.session import get_session
from app.models.user import User
from app.services.activation import ActivationService
from app.services.skills import SkillService

bearer_scheme = HTTPBearer(auto_error=False, description="HS256 access token from POST /auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    request: Request,
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError(
            "An access token is required.", code=ErrorCode.AUTH_REQUIRED
        )

    from app.core.security import decode_access_token  # local import keeps deps import-light

    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
        organization_id = uuid.UUID(str(claims["org"]))
    except (ValueError, KeyError) as exc:
        raise AuthenticationError(
            "Access token claims are malformed.", code=ErrorCode.INVALID_TOKEN
        ) from exc

    # Defence in depth: a validly signed token still cannot act for an
    # organization the user no longer (or never did) belong to.
    user = await UnscopedAuthRepository(session).get_user_in_organization(user_id, organization_id)
    if user is None:
        raise AuthenticationError(
            "Access token does not identify an active user in that organization.",
            code=ErrorCode.INVALID_TOKEN,
        )

    request.state.organization_id = str(user.organization_id)
    request.state.actor_user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_repository(session: SessionDep, user: CurrentUser) -> SkillRepository:
    """Every service in the request gets the same tenant-pinned repository."""
    return SkillRepository(session, user.organization_id)


RepositoryDep = Annotated[SkillRepository, Depends(get_repository)]


async def get_skill_service(repo: RepositoryDep, user: CurrentUser) -> SkillService:
    return SkillService(repo, user)


SkillServiceDep = Annotated[SkillService, Depends(get_skill_service)]


async def get_activation_service(service: SkillServiceDep) -> ActivationService:
    return ActivationService(service)


ActivationServiceDep = Annotated[ActivationService, Depends(get_activation_service)]
