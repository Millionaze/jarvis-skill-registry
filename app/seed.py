"""Idempotent fixture data: two organizations, an owner and a member in each.

Run automatically by the container entrypoint; safe to re-run.

The password comes from SEED_PASSWORD. These are development fixtures, not
credentials for anything real.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import dispose_engine, get_sessionmaker
from app.models.organization import Organization
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("app.seed")

FIXTURES: list[dict[str, object]] = [
    {
        "name": "ABC Construction",
        "slug": "abc-construction",
        "users": [
            {"email": "owner@abc-construction.test", "role": UserRole.OWNER},
            {"email": "member@abc-construction.test", "role": UserRole.MEMBER},
        ],
    },
    {
        "name": "XYZ Builders",
        "slug": "xyz-builders",
        "users": [
            {"email": "owner@xyz-builders.test", "role": UserRole.OWNER},
            {"email": "member@xyz-builders.test", "role": UserRole.MEMBER},
        ],
    },
]


async def seed() -> None:
    settings = get_settings()
    hashed = hash_password(settings.seed_password)

    async with get_sessionmaker()() as session:
        for fixture in FIXTURES:
            slug = str(fixture["slug"])
            org = (
                await session.execute(select(Organization).where(Organization.slug == slug))
            ).scalar_one_or_none()
            if org is None:
                org = Organization(name=str(fixture["name"]), slug=slug)
                session.add(org)
                await session.flush()
                logger.info("created organization %s (%s)", org.name, org.id)
            else:
                logger.info("organization %s already present", org.slug)

            for user_fixture in fixture["users"]:  # type: ignore[union-attr]
                email = str(user_fixture["email"])  # type: ignore[index]
                existing = (
                    await session.execute(select(User).where(User.email == email))
                ).scalar_one_or_none()
                if existing is not None:
                    logger.info("user %s already present", email)
                    continue
                session.add(
                    User(
                        organization_id=org.id,
                        email=email,
                        role=str(user_fixture["role"]),  # type: ignore[index]
                        hashed_password=hashed,
                    )
                )
                logger.info("created user %s (%s)", email, user_fixture["role"])  # type: ignore[index]

        await session.commit()

    await dispose_engine()
    logger.info("seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
