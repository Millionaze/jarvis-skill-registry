"""Audit log.

Covers mandatory test 11, plus the append-only guarantees.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests import flows
from tests.conftest import OrgFixture


async def test_an_audit_record_carries_organization_actor_event_and_version_number(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """Mandatory test 11."""
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]

    audit = await client.get("/audit", headers=abc.owner_headers)
    assert audit.status_code == 200

    entries = audit.json()
    activation = next(entry for entry in entries if entry["event"] == "skill_version.activated")

    assert activation["organization_id"] == str(abc.id)
    assert activation["actor_user_id"] == str(abc.owner.id)
    assert activation["event"] == "skill_version.activated"
    assert activation["skill_id"] == skill_id
    assert activation["skill_version_id"] == active["active_version"]["id"]
    assert activation["version_number"] == 1
    assert activation["payload"]["content_hash"] == active["active_version"]["content_hash"]
    assert activation["created_at"] is not None


async def test_the_exact_activated_version_is_recorded(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """The audit log pins the exact version, by number and by content hash."""
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]

    v2 = await flows.create_version(client, abc.owner_headers, skill_id, prompt_body="second")
    await flows.review(client, abc.owner_headers, skill_id, 2)
    activated = await flows.activate(client, abc.owner_headers, skill_id, 2)

    audit = await client.get("/audit", headers=abc.owner_headers)
    activations = [e for e in audit.json() if e["event"] == "skill_version.activated"]
    by_number = {entry["version_number"]: entry for entry in activations}

    assert set(by_number) == {1, 2}
    assert by_number[1]["payload"]["content_hash"] == active["active_version"]["content_hash"]
    assert by_number[2]["payload"]["content_hash"] == v2["content_hash"]
    assert by_number[2]["payload"]["previous_active_version_number"] == 1
    assert by_number[2]["skill_version_id"] == activated.json()["id"]


async def test_every_lifecycle_step_is_audited(client: AsyncClient, abc: OrgFixture) -> None:
    created = await flows.create_skill(client, abc.owner_headers, requested_tools=["read_project"])
    skill_id = created["id"]

    await client.patch(
        f"/skills/{skill_id}", headers=abc.owner_headers, json={"description": "updated"}
    )
    await client.post(
        f"/skills/{skill_id}/versions/1/tool-grants",
        headers=abc.owner_headers,
        json={"tools": ["read_project"]},
    )
    await flows.review(client, abc.owner_headers, skill_id, 1)
    await flows.activate(client, abc.owner_headers, skill_id, 1)
    await client.post(f"/skills/{skill_id}/disable", headers=abc.owner_headers)

    audit = await client.get("/audit", headers=abc.owner_headers)
    events = {entry["event"] for entry in audit.json()}

    assert {
        "skill.created",
        "skill.updated",
        "skill_version.created",
        "skill_version.reviewed",
        "skill_version.activated",
        "skill_version.disabled",
        "skill.disabled",
        "tool_grant.granted",
    } <= events


async def test_a_failed_state_change_writes_no_audit_row(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """Audit and state share one transaction: if the change fails, so does the log."""
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]

    rejected = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert rejected.status_code == 409

    audit = await client.get("/audit", headers=abc.owner_headers)
    events = [entry["event"] for entry in audit.json()]
    assert "skill_version.activated" not in events


async def test_the_audit_log_cannot_be_updated_by_the_application_role(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    """Append-only: the app role has no UPDATE privilege, and the trigger backs it."""
    await flows.create_reviewed_and_active_skill(client, abc)

    with pytest.raises(DBAPIError) as raised:
        async with session.begin_nested():
            await session.execute(text("UPDATE audit_log SET event = 'tampered'"))

    message = str(raised.value).lower()
    assert "permission denied" in message or "append-only" in message


async def test_the_audit_log_cannot_be_deleted_by_the_application_role(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    await flows.create_reviewed_and_active_skill(client, abc)

    with pytest.raises(DBAPIError) as raised:
        async with session.begin_nested():
            await session.execute(text("DELETE FROM audit_log"))

    message = str(raised.value).lower()
    assert "permission denied" in message or "append-only" in message

    remaining = await session.execute(
        text("SELECT count(*) FROM audit_log WHERE organization_id = :org"), {"org": str(abc.id)}
    )
    assert remaining.scalar_one() > 0


async def test_the_append_only_trigger_is_installed(session: AsyncSession) -> None:
    """Named evidence, so the guarantee survives a careless migration."""
    triggers = await session.execute(
        text(
            "SELECT tgname FROM pg_trigger "
            "WHERE NOT tgisinternal AND tgrelid IN ('audit_log'::regclass, 'skill_versions'::regclass)"
        )
    )
    names = {row[0] for row in triggers}
    assert "trg_audit_log_append_only" in names
    assert "trg_skill_versions_immutable_active" in names
