"""Tenant isolation.

Covers mandatory tests 1-4: same-org read succeeds; cross-org read, update and
activation are all denied with 404 rather than 403.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests import flows
from tests.conftest import OrgFixture


async def test_same_org_create_then_read_succeeds(client: AsyncClient, abc: OrgFixture) -> None:
    """Mandatory test 1."""
    created = await flows.create_skill(client, abc.owner_headers)

    response = await client.get(f"/skills/{created['id']}", headers=abc.owner_headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["id"] == created["id"]
    assert body["organization_id"] == str(abc.id)
    assert body["status"] == "draft"
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version_number"] == 1

    # A member of the same organization sees it too - isolation is per org, not per user.
    as_member = await client.get(f"/skills/{created['id']}", headers=abc.member_headers)
    assert as_member.status_code == 200


async def test_cross_org_read_returns_404_not_403(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """Mandatory test 2.

    404, deliberately: a 403 would confirm that the id names a real row and leak
    the existence of another tenant's data.
    """
    created = await flows.create_skill(client, abc.owner_headers)

    for headers in (xyz.owner_headers, xyz.member_headers):
        response = await client.get(f"/skills/{created['id']}", headers=headers)
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"


async def test_cross_org_update_is_denied(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """Mandatory test 3 - both the metadata update and the create-version write."""
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]

    patched = await client.patch(
        f"/skills/{skill_id}", headers=xyz.owner_headers, json={"description": "taken over"}
    )
    assert patched.status_code == 404
    assert patched.json()["error"]["code"] == "SKILL_NOT_FOUND"

    new_version = await client.post(
        f"/skills/{skill_id}/versions",
        headers=xyz.owner_headers,
        json={"prompt_body": "injected", "requested_tools": []},
    )
    assert new_version.status_code == 404

    reviewed = await client.post(
        f"/skills/{skill_id}/versions/1/review", headers=xyz.owner_headers
    )
    assert reviewed.status_code == 404

    disabled = await client.post(f"/skills/{skill_id}/disable", headers=xyz.owner_headers)
    assert disabled.status_code == 404

    # And nothing actually changed.
    still_there = await client.get(f"/skills/{skill_id}", headers=abc.owner_headers)
    assert still_there.json()["description"] == created["description"]
    assert len(still_there.json()["versions"]) == 1


async def test_cross_org_activation_is_denied_with_404(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """Mandatory test 4.

    The other organization's OWNER gets 404, not 403: the role check is never
    reached because the resource never resolves inside their tenant scope.
    """
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]
    await flows.review(client, abc.owner_headers, skill_id, 1)

    response = await flows.activate(client, xyz.owner_headers, skill_id, 1)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "SKILL_NOT_FOUND"

    # The version is still an unactivated draft.
    detail = await client.get(f"/skills/{skill_id}", headers=abc.owner_headers)
    assert detail.json()["versions"][0]["status"] == "draft"


async def test_listing_only_ever_shows_the_callers_own_organization(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    await flows.create_skill(client, abc.owner_headers, name="ABC Only")
    await flows.create_skill(client, xyz.owner_headers, name="XYZ Only")

    abc_list = await client.get("/skills", headers=abc.owner_headers)
    xyz_list = await client.get("/skills", headers=xyz.owner_headers)

    abc_names = {row["name"] for row in abc_list.json()}
    xyz_names = {row["name"] for row in xyz_list.json()}

    assert abc_names == {"ABC Only"}
    assert xyz_names == {"XYZ Only"}
    assert all(row["organization_id"] == str(abc.id) for row in abc_list.json())
    assert all(row["organization_id"] == str(xyz.id) for row in xyz_list.json())


async def test_the_same_skill_name_may_exist_in_both_organizations(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """Names are tenant-local: uq_skills_organization_id_name, not a global unique."""
    await flows.create_skill(client, abc.owner_headers, name="Invoice Chaser")
    await flows.create_skill(client, xyz.owner_headers, name="Invoice Chaser")

    duplicate = await client.post(
        "/skills",
        headers=abc.owner_headers,
        json={
            "name": "Invoice Chaser",
            "department": "finance",
            "prompt_body": "p",
            "requested_tools": [],
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "SKILL_NAME_CONFLICT"


async def test_organization_id_in_the_request_body_is_rejected(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """Tenancy comes from the token only. A smuggled organization_id is a 422."""
    response = await client.post(
        "/skills",
        headers=abc.owner_headers,
        json={
            "name": "Smuggled",
            "department": "operations",
            "prompt_body": "p",
            "requested_tools": [],
            "organization_id": str(xyz.id),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    listing = await client.get("/skills", headers=abc.owner_headers)
    assert listing.json() == []


async def test_audit_log_is_scoped_to_the_callers_organization(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    await flows.create_skill(client, abc.owner_headers, name="ABC Audit Probe")

    abc_audit = await client.get("/audit", headers=abc.owner_headers)
    xyz_audit = await client.get("/audit", headers=xyz.owner_headers)

    assert len(abc_audit.json()) >= 2
    assert all(entry["organization_id"] == str(abc.id) for entry in abc_audit.json())
    assert xyz_audit.json() == []
