"""Test harness.

Real PostgreSQL, real HTTP through the real ASGI app, real authorization. There
is no in-memory database, no mocked session and nothing that stubs out the
tenancy dependency - overriding it would delete the thing under test.

Isolation strategy: each test runs inside an outer transaction on a dedicated
connection. The session joins it with `join_transaction_mode="create_savepoint"`,
so the application's own `commit()` calls are real (triggers fire, constraints
are checked, the audit row lands) but the outer transaction is rolled back at the
end of the test, leaving the schema pristine for the next one.

The suite connects as the restricted application role (TEST_DATABASE_URL) while
Alembic connects as the schema owner (TEST_MIGRATION_DATABASE_URL) - that is what
makes the REVOKE on audit_log observable from a test.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import subprocess
import sys
import uuid

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_MIGRATION_DATABASE_URL = os.environ.get("TEST_MIGRATION_DATABASE_URL")

if not TEST_DATABASE_URL or not TEST_MIGRATION_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL and TEST_MIGRATION_DATABASE_URL must be set. "
        "Run the suite with: docker compose run --rm api pytest -v --cov"
    )

# Point the application at the test database before anything imports settings.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["MIGRATION_DATABASE_URL"] = TEST_MIGRATION_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-only-not-a-secret")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.enums import UserRole  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_PASSWORD = "test-only-not-a-secret"
#: bcrypt is intentionally slow - hash the fixture password once for the whole run.
_HASHED_TEST_PASSWORD = hash_password(TEST_PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Fresh schema for the session: downgrade to base, then migrate to head."""
    env = {**os.environ, "MIGRATION_DATABASE_URL": TEST_MIGRATION_DATABASE_URL}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def connection(engine):
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture
async def session(connection) -> AsyncSession:
    db = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield db
    finally:
        await db.close()


@dataclasses.dataclass(slots=True)
class OrgFixture:
    """One tenant plus an owner and a member, with ready-made auth headers."""

    organization: Organization
    owner: User
    member: User
    owner_token: str
    member_token: str

    @property
    def id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def owner_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.owner_token}"}

    @property
    def member_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.member_token}"}


async def _create_org(db: AsyncSession, name: str, slug: str) -> OrgFixture:
    suffix = uuid.uuid4().hex[:8]
    organization = Organization(name=name, slug=f"{slug}-{suffix}")
    db.add(organization)
    await db.flush()

    owner = User(
        organization_id=organization.id,
        email=f"owner-{suffix}@{slug}.test",
        role=UserRole.OWNER.value,
        hashed_password=_HASHED_TEST_PASSWORD,
    )
    member = User(
        organization_id=organization.id,
        email=f"member-{suffix}@{slug}.test",
        role=UserRole.MEMBER.value,
        hashed_password=_HASHED_TEST_PASSWORD,
    )
    db.add_all([owner, member])
    await db.flush()

    return OrgFixture(
        organization=organization,
        owner=owner,
        member=member,
        owner_token=create_access_token(
            user_id=owner.id, organization_id=organization.id, role=owner.role
        ),
        member_token=create_access_token(
            user_id=member.id, organization_id=organization.id, role=member.role
        ),
    )


@pytest_asyncio.fixture
async def abc(session: AsyncSession) -> OrgFixture:
    """Fixture organization: ABC Construction."""
    return await _create_org(session, "ABC Construction", "abc-construction")


@pytest_asyncio.fixture
async def xyz(session: AsyncSession) -> OrgFixture:
    """Fixture organization: XYZ Builders."""
    return await _create_org(session, "XYZ Builders", "xyz-builders")


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncClient:
    """The real app, with only the database session swapped for the test one.

    Nothing about authentication or tenancy is overridden.
    """
    application = create_app()

    async def _session_override():
        yield session

    application.dependency_overrides[get_session] = _session_override

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
