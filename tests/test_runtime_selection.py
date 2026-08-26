"""Runtime selection.

Covers mandatory tests 6 and 7: a draft skill can never load as active, and a
disabled skill is excluded.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.db.repository import SkillRepository
from tests import flows
from tests.conftest import OrgFixture


async def test_a_draft_skill_never_loads_as_active(
    client: AsyncClient, abc: OrgFixture, session
) -> None:
    """Mandatory test 6, checked at the API and at the data-access layer."""
    created = await flows.create_skill(client, abc.owner_headers)
    assert created["status"] == "draft"

    runtime = await client.get("/skills/active", headers=abc.owner_headers)
    assert runtime.status_code == 200
    assert runtime.json() == []

    filtered = await client.get(
        "/skills/active", headers=abc.owner_headers, params={"department": "operations"}
    )
    assert filtered.json() == []

    # The same must hold one layer down, so it cannot be reintroduced by a new caller.
    repo = SkillRepository(session, abc.id)
    assert await repo.active_skill_versions() == []
    assert await repo.get_active_version(created["id"]) is None


async def test_a_reviewed_but_unactivated_version_still_does_not_load(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    await flows.review(client, abc.owner_headers, created["id"], 1)

    runtime = await client.get("/skills/active", headers=abc.owner_headers)
    assert runtime.json() == []


async def test_an_active_skill_loads_for_its_department(
    client: AsyncClient, abc: OrgFixture
) -> None:
    active = await flows.create_reviewed_and_active_skill(
        client, abc, name="Ops Digest", department="operations"
    )

    matched = await client.get(
        "/skills/active", headers=abc.owner_headers, params={"department": "operations"}
    )
    assert len(matched.json()) == 1
    assert matched.json()[0]["skill_id"] == active["skill_id"]
    assert matched.json()[0]["version_number"] == 1

    other_department = await client.get(
        "/skills/active", headers=abc.owner_headers, params={"department": "finance"}
    )
    assert other_department.json() == []


async def test_a_disabled_skill_is_excluded_from_runtime_selection(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """Mandatory test 7."""
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]

    before = await client.get("/skills/active", headers=abc.owner_headers)
    assert len(before.json()) == 1

    disabled = await client.post(f"/skills/{skill_id}/disable", headers=abc.owner_headers)
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["versions"][0]["status"] == "disabled"

    after = await client.get("/skills/active", headers=abc.owner_headers)
    assert after.json() == []

    unfiltered = await client.get(
        "/skills/active", headers=abc.owner_headers, params={"department": "operations"}
    )
    assert unfiltered.json() == []


async def test_a_disabled_skill_cannot_be_reactivated_or_edited(
    client: AsyncClient, abc: OrgFixture
) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)
    skill_id = active["skill_id"]
    await client.post(f"/skills/{skill_id}/disable", headers=abc.owner_headers)

    new_version = await client.post(
        f"/skills/{skill_id}/versions",
        headers=abc.owner_headers,
        json={"prompt_body": "p", "requested_tools": []},
    )
    assert new_version.status_code == 409
    assert new_version.json()["error"]["code"] == "SKILL_DISABLED"

    patched = await client.patch(
        f"/skills/{skill_id}", headers=abc.owner_headers, json={"description": "x"}
    )
    assert patched.status_code == 409


async def test_only_an_owner_can_disable_a_skill(client: AsyncClient, abc: OrgFixture) -> None:
    active = await flows.create_reviewed_and_active_skill(client, abc)

    denied = await client.post(
        f"/skills/{active['skill_id']}/disable", headers=abc.member_headers
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "NOT_ORG_OWNER"


async def test_runtime_selection_never_crosses_organizations(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    await flows.create_reviewed_and_active_skill(client, abc, name="ABC Runtime")
    await flows.create_reviewed_and_active_skill(client, xyz, name="XYZ Runtime")

    abc_runtime = await client.get("/skills/active", headers=abc.owner_headers)
    xyz_runtime = await client.get("/skills/active", headers=xyz.owner_headers)

    assert [row["name"] for row in abc_runtime.json()] == ["ABC Runtime"]
    assert [row["name"] for row in xyz_runtime.json()] == ["XYZ Runtime"]
    assert abc_runtime.json()[0]["organization_id"] == str(abc.id)
