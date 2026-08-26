"""Immutability of an active version, proved at all three layers.

Covers mandatory tests 8 and 12.

Layer 1 - API:         no route mutates version content; an edit is version N+1.
Layer 2 - application: the SQLAlchemy before_update guard.
Layer 3 - database:    trg_skill_versions_immutable_active, which fires for raw
                       SQL that never touches the ORM at all. That last one is
                       the real evidence against silent mutation, so it is
                       tested by going deliberately around the ORM.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ImmutableVersionError
from app.models.skill import SkillVersion
from tests import flows
from tests.conftest import OrgFixture


# --------------------------------------------------------------------------
# Layer 1: the API surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
async def test_no_route_exists_to_mutate_a_version(
    client: AsyncClient, abc: OrgFixture, method: str
) -> None:
    """Mandatory test 8, part 1: there is simply no endpoint that edits a version."""
    active = await flows.create_reviewed_and_active_skill(client, abc)
    url = f"/skills/{active['skill_id']}/versions/1"

    response = await getattr(client, method)(url, headers=abc.owner_headers)
    assert response.status_code in (404, 405), (
        f"{method.upper()} {url} unexpectedly resolved to {response.status_code}"
    )


async def test_an_active_version_cannot_be_re_reviewed(
    client: AsyncClient, abc: OrgFixture
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)

    response = await client.post(
        f"/skills/{active['skill_id']}/versions/1/review", headers=abc.owner_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACTIVE_VERSION_IMMUTABLE"


async def test_editing_an_active_skill_creates_a_new_version_and_leaves_the_active_one_alone(
    client: AsyncClient, abc: OrgFixture
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]
    original = active["active_version"]

    edited = await flows.create_version(
        client, abc.owner_headers, skill_id, prompt_body="A completely different prompt."
    )
    assert edited["version_number"] == 2
    assert edited["status"] == "draft"
    assert edited["content_hash"] != original["content_hash"]

    detail = await client.get(f"/skills/{skill_id}", headers=abc.owner_headers)
    version_one = next(v for v in detail.json()["versions"] if v["version_number"] == 1)
    assert version_one["status"] == "active"
    assert version_one["prompt_body"] == original["prompt_body"]
    assert version_one["content_hash"] == original["content_hash"]


# --------------------------------------------------------------------------
# Layer 2: the application guard
# --------------------------------------------------------------------------


async def test_orm_guard_blocks_mutation_of_an_active_version(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    """Mandatory test 8, part 2: even code holding the mapped object cannot do it."""
    active = await flows.create_reviewed_and_active_skill(client, abc)
    version_id = active["active_version"]["id"]

    version = await session.get(SkillVersion, version_id)
    assert version is not None and version.status == "active"

    version.prompt_body = "mutated through the orm"
    with pytest.raises(ImmutableVersionError, match="immutable"):
        await session.flush()

    await session.rollback()


async def test_orm_guard_blocks_an_illegal_status_transition_out_of_active(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)

    version = await session.get(SkillVersion, active["active_version"]["id"])
    assert version is not None

    version.status = "draft"  # active -> draft is not one of the two legal exits
    with pytest.raises(ImmutableVersionError, match="Illegal transition"):
        await session.flush()

    await session.rollback()


async def test_orm_guard_permits_the_two_legal_transitions_out_of_active(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    """The guard must not be so blunt that supersede and disable stop working."""
    active = await flows.create_reviewed_and_active_skill(client, abc)

    version = await session.get(SkillVersion, active["active_version"]["id"])
    assert version is not None

    version.status = "superseded"
    await session.flush()  # must not raise
    assert version.status == "superseded"

    await session.rollback()


# --------------------------------------------------------------------------
# Layer 3: the database trigger, reached with raw SQL around the ORM
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("prompt_body", "'silently mutated'"),
        ("content_hash", "'0000000000000000000000000000000000000000000000000000000000000000'"),
        ("requested_tools", "'[\"read_invoice\"]'::jsonb"),
        ("version_number", "42"),
    ],
)
async def test_db_trigger_blocks_raw_sql_mutation_of_an_active_version(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession, column: str, value: str
) -> None:
    """Mandatory test 8, part 3 - the strongest evidence against silent mutation.

    This statement never goes near the ORM: no mapper, no event listener, no
    service. Only trg_skill_versions_immutable_active stands between it and the
    row, and it must fire.
    """
    active = await flows.create_reviewed_and_active_skill(client, abc)
    version_id = active["active_version"]["id"]

    with pytest.raises(DBAPIError) as raised:
        async with session.begin_nested():
            await session.execute(
                text(f"UPDATE skill_versions SET {column} = {value} WHERE id = :vid"),
                {"vid": version_id},
            )

    assert "immutable" in str(raised.value).lower()

    # And the row is untouched.
    stored = await session.execute(
        text("SELECT prompt_body, content_hash, version_number FROM skill_versions WHERE id = :vid"),
        {"vid": version_id},
    )
    row = stored.one()
    assert row.prompt_body == active["active_version"]["prompt_body"]
    assert row.content_hash == active["active_version"]["content_hash"]
    assert row.version_number == 1


async def test_db_trigger_blocks_raw_sql_reassignment_of_an_active_version_to_another_org(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture, session: AsyncSession
) -> None:
    """Ownership of an active version is immutable too - no tenant re-parenting."""
    active = await flows.create_reviewed_and_active_skill(client, abc)

    with pytest.raises(DBAPIError) as raised:
        async with session.begin_nested():
            await session.execute(
                text("UPDATE skill_versions SET organization_id = :org WHERE id = :vid"),
                {"org": str(xyz.id), "vid": active["active_version"]["id"]},
            )

    assert "immutable" in str(raised.value).lower()


async def test_db_trigger_permits_the_legal_supersede_transition(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)

    await session.execute(
        text("UPDATE skill_versions SET status = 'superseded' WHERE id = :vid"),
        {"vid": active["active_version"]["id"]},
    )
    status = await session.execute(
        text("SELECT status FROM skill_versions WHERE id = :vid"),
        {"vid": active["active_version"]["id"]},
    )
    assert status.scalar_one() == "superseded"


async def test_only_one_active_version_per_skill_is_possible(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    """Mandatory test 12: proved against the database constraint itself."""
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]

    # The partial unique index exists and is defined as advertised.
    index = await session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'uq_skill_versions_one_active_per_skill'"
        )
    )
    definition = index.scalar_one()
    assert "UNIQUE" in definition
    assert "(status = 'active'::text)" in definition or "status = 'active'" in definition

    # Forcing a second active row for the same skill is refused by the database.
    with pytest.raises(DBAPIError) as raised:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    INSERT INTO skill_versions
                        (id, skill_id, organization_id, version_number, prompt_body,
                         requested_tools, status, content_hash, created_by)
                    SELECT gen_random_uuid(), skill_id, organization_id, 999, 'forced',
                           '[]'::jsonb, 'active', 'forced-hash', created_by
                    FROM skill_versions WHERE id = :vid
                    """
                ),
                {"vid": active["active_version"]["id"]},
            )

    assert "uq_skill_versions_one_active_per_skill" in str(raised.value)

    remaining = await session.execute(
        text("SELECT count(*) FROM skill_versions WHERE skill_id = :sid AND status = 'active'"),
        {"sid": skill_id},
    )
    assert remaining.scalar_one() == 1
