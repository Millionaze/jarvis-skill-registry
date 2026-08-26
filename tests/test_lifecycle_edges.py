"""Lifecycle edge cases and the repository's own guards."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import ScopedRepository
from app.main import create_app, lifespan
from app.models.organization import Organization
from tests import flows
from tests.conftest import OrgFixture


async def test_health_is_open(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_the_application_lifespan_starts_and_stops_cleanly() -> None:
    """Startup must resolve settings (proving JWT_SECRET is present) and shut down
    without leaving an engine behind."""
    from app.core.config import get_settings
    from app.db import session as session_module

    application = create_app()
    async with lifespan(application):
        settings = get_settings()
        assert settings.jwt_secret, "startup must fail loudly rather than run unsigned"
        assert settings.database_url.startswith("postgresql+asyncpg://")

    # Suppressing SLF001 here: reaching into module state is the assertion, not a shortcut -
    # "the engine was disposed" is only observable there.
    assert session_module._engine is None, (  # noqa: SLF001
        "lifespan must dispose the engine on shutdown"
    )


async def test_updating_skill_metadata_records_the_change(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers, department="operations")

    response = await client.patch(
        f"/skills/{created['id']}",
        headers=abc.owner_headers,
        json={"department": "finance", "description": "Moved to finance."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["department"] == "finance"
    assert response.json()["description"] == "Moved to finance."

    audit = await client.get("/audit", headers=abc.owner_headers)
    updates = [entry for entry in audit.json() if entry["event"] == "skill.updated"]
    assert updates[0]["payload"]["changes"] == {
        "department": "finance",
        "description": "Moved to finance.",
    }


async def test_an_empty_metadata_update_changes_nothing_and_is_not_audited(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)

    response = await client.patch(f"/skills/{created['id']}", headers=abc.owner_headers, json={})
    assert response.status_code == 200
    assert response.json()["department"] == created["department"]

    audit = await client.get("/audit", headers=abc.owner_headers)
    assert [e for e in audit.json() if e["event"] == "skill.updated"] == []


async def test_a_superseded_version_cannot_be_reviewed(
    client: AsyncClient, abc: OrgFixture
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]
    await flows.create_version(client, abc.owner_headers, skill_id)
    await flows.review(client, abc.owner_headers, skill_id, 2)
    await flows.activate(client, abc.owner_headers, skill_id, 2)

    response = await client.post(
        f"/skills/{skill_id}/versions/1/review", headers=abc.owner_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_NOT_ACTIVATABLE"


async def test_disabling_an_already_disabled_skill_is_idempotent(
    client: AsyncClient, abc: OrgFixture
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]

    first = await client.post(f"/skills/{skill_id}/disable", headers=abc.owner_headers)
    second = await client.post(f"/skills/{skill_id}/disable", headers=abc.owner_headers)
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "disabled"

    audit = await client.get("/audit", headers=abc.owner_headers)
    disables = [entry for entry in audit.json() if entry["event"] == "skill.disabled"]
    assert len(disables) == 1


async def test_a_version_of_a_disabled_skill_cannot_be_activated(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]
    await flows.review(client, abc.owner_headers, skill_id, 1)
    await client.post(f"/skills/{skill_id}/disable", headers=abc.owner_headers)

    response = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SKILL_DISABLED"


async def test_disabling_a_draft_skill_touches_no_version(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)

    response = await client.post(f"/skills/{created['id']}/disable", headers=abc.owner_headers)
    assert response.status_code == 200
    assert response.json()["versions"][0]["status"] == "draft"


def test_the_repository_refuses_a_model_that_is_not_tenant_owned(session: AsyncSession) -> None:
    """Organizations are not tenant-owned rows - they ARE the tenant."""
    repo = ScopedRepository(session, uuid.uuid4())

    with pytest.raises(TypeError, match="not a tenant-owned model"):
        repo.select(Organization)

    with pytest.raises(TypeError, match="not a tenant-owned model"):
        repo.add(Organization(name="Sneaky", slug="sneaky"))


async def test_the_repository_overwrites_any_organization_id_it_is_handed(
    session: AsyncSession, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """Even if calling code sets organization_id itself, the token's wins."""
    from app.models.skill import Skill

    repo = ScopedRepository(session, abc.id)
    skill = Skill(
        organization_id=xyz.id,  # deliberately wrong
        name="Stamped",
        department="operations",
        description="",
        status="draft",
        created_by=abc.owner.id,
    )
    repo.add(skill)
    await repo.flush()

    assert skill.organization_id == abc.id


async def test_a_lost_race_on_a_duplicate_skill_name_is_a_409_not_a_500(
    client: AsyncClient, abc: OrgFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: two concurrent creates can both pass the pre-check.

    Found by the pre-submission audit - concurrent POST /skills with the same name
    returned 500 INTERNAL_ERROR because the resulting IntegrityError was unhandled.
    The pre-check is only a fast path; uq_skills_organization_id_name is the
    authority, and losing that race is a conflict, not a server error.

    The race window is reproduced deterministically by making the pre-check miss,
    which is exactly what the losing request observes.
    """
    from app.db.repository import SkillRepository

    body = {
        "name": "Contended Name",
        "department": "operations",
        "prompt_body": "p",
        "requested_tools": [],
    }
    first = await client.post("/skills", headers=abc.owner_headers, json=body)
    assert first.status_code == 201

    async def _pretend_the_name_is_free(self, name: str):
        return None

    monkeypatch.setattr(SkillRepository, "find_skill_by_name", _pretend_the_name_is_free)

    second = await client.post("/skills", headers=abc.owner_headers, json=body)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "SKILL_NAME_CONFLICT"
    assert second.json()["error"]["detail"]["name"] == "Contended Name"

    # The losing request left nothing behind and the session still works.
    monkeypatch.undo()
    listing = await client.get("/skills", headers=abc.owner_headers)
    assert [row["name"] for row in listing.json()] == ["Contended Name"]


async def test_an_unrelated_constraint_violation_is_not_mislabelled_as_a_name_conflict(
    client: AsyncClient, abc: OrgFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_skill only claims SKILL_NAME_CONFLICT for the name constraint.

    Any other IntegrityError is re-raised and handled generically, so a future
    constraint cannot be silently reported as a duplicate-name error.
    """
    from sqlalchemy.exc import IntegrityError

    from app.db.repository import SkillRepository

    async def _raise_a_different_constraint(self) -> None:
        raise IntegrityError(
            "INSERT INTO skills ...",
            {},
            Exception('violates foreign key constraint "fk_skills_created_by_users"'),
        )

    monkeypatch.setattr(SkillRepository, "flush", _raise_a_different_constraint)

    response = await client.post(
        "/skills",
        headers=abc.owner_headers,
        json={
            "name": "Unrelated Constraint",
            "department": "operations",
            "prompt_body": "p",
            "requested_tools": [],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSTRAINT_VIOLATION"
    assert response.json()["error"]["code"] != "SKILL_NAME_CONFLICT"
