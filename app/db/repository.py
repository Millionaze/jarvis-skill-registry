"""Organization-scoped data access.

This module is the ONLY place a tenant-owned table is queried. Services never
touch `AsyncSession` directly and never build their own `select()`; they are
handed a `ScopedRepository` that has an `organization_id` baked in, so every
statement it produces already carries `model.organization_id == <caller's org>`.

That is the structural half of tenant isolation: forgetting the filter is not a
mistake you can make in a service, because a service has no way to express an
unfiltered query. `tests/test_structure.py` enforces that invariant in CI.

The one pre-tenant operation - looking a user up by email at login, before any
organization is known - lives in `UnscopedAuthRepository`, named so that its
unscoped-ness is explicit and greppable rather than accidental.
"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ErrorCode, ResourceNotFoundError
from app.db.base import Base
from app.models.skill import Skill, SkillVersion
from app.models.user import User

ModelT = TypeVar("ModelT", bound=Base)


class ScopedRepository:
    """A session view pinned to exactly one organization."""

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    @property
    def organization_id(self) -> uuid.UUID:
        return self._organization_id

    # -- statement construction -------------------------------------------

    def owned(self, model: type[ModelT]) -> ColumnElement[bool]:
        """The tenancy predicate for `model`. Use when joining a second table."""
        column = getattr(model, "organization_id", None)
        if column is None:
            raise TypeError(f"{model.__name__} is not a tenant-owned model")
        return column == self._organization_id

    def select(self, model: type[ModelT]) -> Select[tuple[ModelT]]:
        """A SELECT that is already scoped to this organization."""
        return select(model).where(self.owned(model))

    # -- reads -------------------------------------------------------------

    async def get(self, model: type[ModelT], id_: uuid.UUID) -> ModelT | None:
        stmt = self.select(model).where(model.id == id_)  # type: ignore[attr-defined]
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def require(
        self, model: type[ModelT], id_: uuid.UUID, *, code: str, message: str
    ) -> ModelT:
        """Fetch or raise 404.

        A row that exists but belongs to another organization is indistinguishable
        from a row that does not exist - that is the point (see ARCHITECTURE.md).
        """
        instance = await self.get(model, id_)
        if instance is None:
            raise ResourceNotFoundError(message, code=code, detail={"id": str(id_)})
        return instance

    async def scalars(self, stmt: Select[Any]) -> list[Any]:
        return list((await self._session.execute(stmt)).scalars().all())

    async def scalar_one_or_none(self, stmt: Select[Any]) -> Any:
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # -- writes ------------------------------------------------------------

    def add(self, instance: ModelT) -> ModelT:
        """Attach a new row, forcing its organization_id to the caller's.

        Any organization_id already on the instance is overwritten, never trusted.
        """
        if not hasattr(instance, "organization_id"):
            raise TypeError(f"{type(instance).__name__} is not a tenant-owned model")
        instance.organization_id = self._organization_id  # type: ignore[attr-defined]
        self._session.add(instance)
        return instance

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        """Return the session to a usable state after a constraint violation."""
        await self._session.rollback()


class SkillRepository(ScopedRepository):
    """Skill-shaped reads that need more than a plain scoped SELECT."""

    async def get_skill_with_versions(self, skill_id: uuid.UUID) -> Skill | None:
        stmt = (
            self.select(Skill)
            .where(Skill.id == skill_id)
            .options(selectinload(Skill.versions).selectinload(SkillVersion.tool_grants))
        )
        return await self.scalar_one_or_none(stmt)

    async def list_skills(self) -> list[Skill]:
        stmt = self.select(Skill).order_by(Skill.created_at.desc())
        return await self.scalars(stmt)

    async def get_version(self, skill_id: uuid.UUID, version_number: int) -> SkillVersion | None:
        stmt = (
            self.select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .where(SkillVersion.version_number == version_number)
            .options(selectinload(SkillVersion.tool_grants))
        )
        return await self.scalar_one_or_none(stmt)

    async def get_active_version(self, skill_id: uuid.UUID) -> SkillVersion | None:
        stmt = (
            self.select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .where(SkillVersion.status == "active")
            .options(selectinload(SkillVersion.tool_grants))
        )
        return await self.scalar_one_or_none(stmt)

    async def lock_skill(self, skill_id: uuid.UUID) -> Skill | None:
        """Row-lock a skill so concurrent writers serialise on version numbering
        and on the single-active-version transition."""
        stmt = self.select(Skill).where(Skill.id == skill_id).with_for_update()
        return await self.scalar_one_or_none(stmt)

    async def next_version_number(self, skill_id: uuid.UUID) -> int:
        stmt = (
            select(func.coalesce(func.max(SkillVersion.version_number), 0) + 1)
            .where(self.owned(SkillVersion))
            .where(SkillVersion.skill_id == skill_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def find_skill_by_name(self, name: str) -> Skill | None:
        stmt = self.select(Skill).where(Skill.name == name)
        return await self.scalar_one_or_none(stmt)

    async def active_skill_versions(
        self, department: str | None = None
    ) -> list[tuple[Skill, SkillVersion]]:
        """Runtime selection: only active skills that have an active version.

        Both sides of the join are scoped independently - `skills` by its own
        organization_id and `skill_versions` by its denormalised one.
        """
        stmt = (
            select(Skill, SkillVersion)
            .join(SkillVersion, SkillVersion.skill_id == Skill.id)
            .where(self.owned(Skill))
            .where(self.owned(SkillVersion))
            .where(Skill.status == "active")
            .where(SkillVersion.status == "active")
            .options(selectinload(SkillVersion.tool_grants))
            .order_by(Skill.name)
        )
        if department is not None:
            stmt = stmt.where(Skill.department == department)
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]


class UnscopedAuthRepository:
    """The single deliberately unscoped repository.

    Login has to find a user before an organization is known. Nothing else in
    the codebase queries without a tenant predicate.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_user_in_organization(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> User | None:
        """Re-validate a token's (user, org) pairing against the database.

        Defence in depth: even a validly signed token cannot act for an
        organization the user does not belong to.
        """
        stmt = (
            select(User)
            .where(User.id == user_id)
            .where(User.organization_id == organization_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "ScopedRepository",
    "SkillRepository",
    "UnscopedAuthRepository",
    "ResourceNotFoundError",
    "ErrorCode",
]
