"""The fixture seed.

`docker compose up` runs this before serving, so a broken seed means a broken
first-run experience. It is covered like any other module rather than omitted
from the coverage report.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.security import verify_password
from app.models.organization import Organization
from app.models.user import User
from app.seed import FIXTURES, seed


def test_the_fixtures_are_the_two_organizations_the_brief_names() -> None:
    by_name = {fixture.name: fixture for fixture in FIXTURES}
    assert set(by_name) == {"ABC Construction", "XYZ Builders"}

    for fixture in FIXTURES:
        roles = sorted(user.role for user in fixture.users)
        assert roles == [UserRole.MEMBER, UserRole.OWNER], f"{fixture.name} needs one of each"
        assert len({user.email for user in fixture.users}) == 2


async def test_seeding_creates_both_organizations_with_an_owner_and_a_member(
    session: AsyncSession,
) -> None:
    await seed()

    for fixture in FIXTURES:
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == fixture.slug)
            )
        ).scalar_one()
        assert org.name == fixture.name

        users = list(
            (
                await session.execute(select(User).where(User.organization_id == org.id))
            ).scalars()
        )
        by_email = {user.email: user for user in users}

        for expected in fixture.users:
            created = by_email[expected.email]
            assert created.role == expected.role.value
            assert created.organization_id == org.id
            # A real bcrypt hash, and the documented seed password verifies against it.
            assert created.hashed_password.startswith("$2b$")
            assert verify_password("dev-only-not-a-secret", created.hashed_password)


async def test_seeding_twice_is_idempotent(session: AsyncSession) -> None:
    """The entrypoint re-runs it on every container start."""
    await seed()

    first_orgs = len(list((await session.execute(select(Organization))).scalars()))
    first_users = len(list((await session.execute(select(User))).scalars()))

    await seed()

    assert len(list((await session.execute(select(Organization))).scalars())) == first_orgs
    assert len(list((await session.execute(select(User))).scalars())) == first_users
