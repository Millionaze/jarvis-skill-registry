"""Idempotent fixture data: two organizations, an owner and a member in each.

Run automatically by the container entrypoint; safe to re-run.

The password comes from SEED_PASSWORD. These are development fixtures, not
credentials for anything real.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import dispose_engine, get_sessionmaker
from app.models.organization import Organization
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("app.seed")

@dataclass(frozen=True, slots=True)
class UserFixture:
    email: str
    role: UserRole


@dataclass(frozen=True, slots=True)
class OrganizationFixture:
    name: str
    slug: str
    users: tuple[UserFixture, ...]


FIXTURES: tuple[OrganizationFixture, ...] = (
    OrganizationFixture(
        name="ABC Construction",
        slug="abc-construction",
        users=(
            UserFixture("owner@abc-construction.test", UserRole.OWNER),
            UserFixture("member@abc-construction.test", UserRole.MEMBER),
        ),
    ),
    OrganizationFixture(
        name="XYZ Builders",
        slug="xyz-builders",
        users=(
            UserFixture("owner@xyz-builders.test", UserRole.OWNER),
            UserFixture("member@xyz-builders.test", UserRole.MEMBER),
        ),
    ),
)


async def seed() -> None:
    settings = get_settings()
    hashed = hash_password(settings.seed_password)

    async with get_sessionmaker()() as session:
        for fixture in FIXTURES:
            org = (
                await session.execute(
                    select(Organization).where(Organization.slug == fixture.slug)
                )
            ).scalar_one_or_none()
            if org is None:
                org = Organization(name=fixture.name, slug=fixture.slug)
                session.add(org)
                await session.flush()
                logger.info("created organization %s (%s)", org.name, org.id)
            else:
                logger.info("organization %s already present", org.slug)

            for user_fixture in fixture.users:
                existing = (
                    await session.execute(select(User).where(User.email == user_fixture.email))
                ).scalar_one_or_none()
                if existing is not None:
                    logger.info("user %s already present", user_fixture.email)
                    continue
                session.add(
                    User(
                        organization_id=org.id,
                        email=user_fixture.email,
                        role=user_fixture.role.value,
                        hashed_password=hashed,
                    )
                )
                logger.info("created user %s (%s)", user_fixture.email, user_fixture.role.value)

        await session.commit()

    await dispose_engine()
    logger.info("seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
