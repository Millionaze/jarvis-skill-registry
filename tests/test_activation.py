"""Activation: owner-only, review-gated, idempotent, atomic supersede.

Covers mandatory tests 5 and 9.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests import flows
from tests.conftest import OrgFixture


async def test_member_cannot_activate_and_gets_403(client: AsyncClient, abc: OrgFixture) -> None:
    """Mandatory test 5.

    403 here, not 404: the member CAN see this skill, so hiding it would be a
    lie. Only the role is insufficient.
    """
    created = await flows.create_skill(client, abc.member_headers)
    skill_id = created["id"]
    await flows.review(client, abc.member_headers, skill_id, 1)

    response = await flows.activate(client, abc.member_headers, skill_id, 1)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "NOT_ORG_OWNER"
    assert response.json()["error"]["detail"]["required_role"] == "owner"

    detail = await client.get(f"/skills/{skill_id}", headers=abc.member_headers)
    assert detail.json()["versions"][0]["status"] == "draft"


async def test_an_unreviewed_version_cannot_be_activated(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """There is no automatic activation anywhere: review is a hard gate."""
    created = await flows.create_skill(client, abc.owner_headers)

    response = await flows.activate(client, abc.owner_headers, created["id"], 1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_NOT_REVIEWED"


async def test_a_freshly_created_skill_is_never_automatically_active(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    assert created["status"] == "draft"
    assert created["versions"][0]["status"] == "draft"
    assert created["versions"][0]["activated_at"] is None
    assert created["versions"][0]["activated_by"] is None


async def test_owner_activates_a_reviewed_version(client: AsyncClient, abc: OrgFixture) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]
    await flows.review(client, abc.owner_headers, skill_id, 1)

    response = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert response.status_code == 200, response.text
    assert response.headers["X-Activation-Changed"] == "true"

    version = response.json()
    assert version["status"] == "active"
    assert version["activated_at"] is not None
    assert version["activated_by"] == str(abc.owner.id)

    detail = await client.get(f"/skills/{skill_id}", headers=abc.owner_headers)
    assert detail.json()["status"] == "active"


async def test_duplicate_activation_is_idempotent_and_writes_no_duplicate_audit(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """Mandatory test 9."""
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]
    await flows.review(client, abc.owner_headers, skill_id, 1)

    first = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert first.status_code == 200
    assert first.headers["X-Activation-Changed"] == "true"

    second = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert second.status_code == 200, second.text
    assert second.headers["X-Activation-Changed"] == "false"

    # State is byte-for-byte unchanged, including the activation timestamp.
    assert second.json() == first.json()

    third = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert third.status_code == 200
    assert third.json() == first.json()

    audit = await client.get("/audit", headers=abc.owner_headers)
    activations = [
        entry
        for entry in audit.json()
        if entry["event"] == "skill_version.activated" and entry["skill_id"] == skill_id
    ]
    assert len(activations) == 1, f"expected exactly one activation audit row, got {activations}"


async def test_activating_a_second_version_supersedes_the_first_atomically(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]
    await flows.review(client, abc.owner_headers, skill_id, 1)
    await flows.activate(client, abc.owner_headers, skill_id, 1)

    v2 = await flows.create_version(client, abc.owner_headers, skill_id, prompt_body="v2 prompt")
    assert v2["version_number"] == 2
    await flows.review(client, abc.owner_headers, skill_id, 2)

    response = await flows.activate(client, abc.owner_headers, skill_id, 2)
    assert response.status_code == 200, response.text

    detail = await client.get(f"/skills/{skill_id}", headers=abc.owner_headers)
    by_number = {v["version_number"]: v for v in detail.json()["versions"]}
    assert by_number[1]["status"] == "superseded"
    assert by_number[2]["status"] == "active"

    # Version 1's content survived being superseded untouched.
    assert by_number[1]["prompt_body"] == created["versions"][0]["prompt_body"]
    assert by_number[1]["content_hash"] == created["versions"][0]["content_hash"]

    count = await session.execute(
        text(
            "SELECT count(*) FROM skill_versions WHERE skill_id = :sid AND status = 'active'"
        ),
        {"sid": skill_id},
    )
    assert count.scalar_one() == 1

    audit = await client.get("/audit", headers=abc.owner_headers)
    events = [entry["event"] for entry in audit.json()]
    assert "skill_version.superseded" in events


async def test_a_superseded_version_cannot_be_reactivated(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]
    await flows.review(client, abc.owner_headers, skill_id, 1)
    await flows.activate(client, abc.owner_headers, skill_id, 1)
    await flows.create_version(client, abc.owner_headers, skill_id)
    await flows.review(client, abc.owner_headers, skill_id, 2)
    await flows.activate(client, abc.owner_headers, skill_id, 2)

    response = await flows.activate(client, abc.owner_headers, skill_id, 1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_NOT_ACTIVATABLE"


async def test_activating_a_missing_version_is_404(client: AsyncClient, abc: OrgFixture) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    response = await flows.activate(client, abc.owner_headers, created["id"], 99)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SKILL_VERSION_NOT_FOUND"
