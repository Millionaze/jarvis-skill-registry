"""Tool permissions.

Covers mandatory test 10: unknown tools rejected, destructive tools rejected,
and a requested tool is never auto-granted.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools import ALLOWED_TOOLS
from tests import flows
from tests.conftest import OrgFixture


@pytest.mark.parametrize("tool", ["read_everything", "list_all_orgs", "admin_panel", "no_such_tool"])
async def test_an_unknown_tool_is_rejected_with_422(
    client: AsyncClient, abc: OrgFixture, tool: str
) -> None:
    response = await client.post(
        "/skills",
        headers=abc.owner_headers,
        json={
            "name": f"Probe {tool}",
            "department": "operations",
            "prompt_body": "p",
            "requested_tools": [tool],
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "UNKNOWN_TOOL"
    assert error["detail"]["tool"] == tool
    assert sorted(ALLOWED_TOOLS) == error["detail"]["allowed_tools"]


@pytest.mark.parametrize(
    "tool",
    [
        "shell_exec",
        "drop_table",
        "delete_all",
        "sudo",
        "rm",
        "read_*",
        "../../etc/passwd",
        "read_project; rm -rf /",
        "tools/read_project",
        "read project",
        "`whoami`",
    ],
)
async def test_a_destructive_or_malformed_tool_is_rejected_with_422(
    client: AsyncClient, abc: OrgFixture, tool: str
) -> None:
    response = await client.post(
        "/skills",
        headers=abc.owner_headers,
        json={
            "name": "Probe destructive",
            "department": "operations",
            "prompt_body": "p",
            "requested_tools": [tool],
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "FORBIDDEN_TOOL_PATTERN", error
    assert error["detail"]["tool"] == tool
    assert "reason" in error["detail"]


async def test_a_rejected_tool_creates_nothing_at_all(
    client: AsyncClient, abc: OrgFixture
) -> None:
    await client.post(
        "/skills",
        headers=abc.owner_headers,
        json={
            "name": "Should Not Exist",
            "department": "operations",
            "prompt_body": "p",
            "requested_tools": ["query_schedule", "shell_exec"],
        },
    )
    listing = await client.get("/skills", headers=abc.owner_headers)
    assert listing.json() == []


async def test_a_requested_tool_is_never_auto_granted(
    client: AsyncClient, abc: OrgFixture, session: AsyncSession
) -> None:
    """Mandatory test 10, part 3."""
    created = await flows.create_skill(
        client,
        abc.owner_headers,
        requested_tools=["query_schedule", "read_project", "read_invoice"],
    )
    grants = created["versions"][0]["tool_grants"]
    assert len(grants) == 3
    assert all(grant["granted"] is False for grant in grants)
    assert all(grant["granted_by"] is None for grant in grants)
    assert all(grant["granted_at"] is None for grant in grants)

    # Also true in the database, not just in the response shape.
    ungranted = await session.execute(
        text("SELECT count(*) FROM tool_grants WHERE granted IS TRUE")
    )
    assert ungranted.scalar_one() == 0


async def test_only_an_owner_can_grant_tools(client: AsyncClient, abc: OrgFixture) -> None:
    created = await flows.create_skill(client, abc.member_headers)

    denied = await client.post(
        f"/skills/{created['id']}/versions/1/tool-grants",
        headers=abc.member_headers,
        json={"tools": ["query_schedule"]},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "NOT_ORG_OWNER"

    allowed = await client.post(
        f"/skills/{created['id']}/versions/1/tool-grants",
        headers=abc.owner_headers,
        json={"tools": ["query_schedule"]},
    )
    assert allowed.status_code == 200, allowed.text
    granted = {g["tool_name"]: g for g in allowed.json()["tool_grants"]}
    assert granted["query_schedule"]["granted"] is True
    assert granted["query_schedule"]["granted_by"] == str(abc.owner.id)


async def test_an_owner_from_another_org_cannot_grant_tools(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)

    response = await client.post(
        f"/skills/{created['id']}/versions/1/tool-grants",
        headers=xyz.owner_headers,
        json={"tools": ["query_schedule"]},
    )
    assert response.status_code == 404


async def test_a_tool_that_was_never_requested_cannot_be_granted(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers, requested_tools=["query_schedule"])

    response = await client.post(
        f"/skills/{created['id']}/versions/1/tool-grants",
        headers=abc.owner_headers,
        json={"tools": ["read_invoice"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TOOL_NOT_REQUESTED"


async def test_runtime_selection_only_ever_exposes_granted_tools(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(
        client, abc.owner_headers, requested_tools=["query_schedule", "read_project"]
    )
    skill_id = created["id"]
    await client.post(
        f"/skills/{skill_id}/versions/1/tool-grants",
        headers=abc.owner_headers,
        json={"tools": ["query_schedule"]},
    )
    await flows.review(client, abc.owner_headers, skill_id, 1)
    await flows.activate(client, abc.owner_headers, skill_id, 1)

    runtime = await client.get("/skills/active", headers=abc.owner_headers)
    payload = runtime.json()[0]
    assert payload["granted_tools"] == ["query_schedule"]
    assert "read_project" not in payload["granted_tools"]


async def test_granting_twice_is_idempotent_and_writes_one_audit_row(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers, requested_tools=["read_project"])
    url = f"/skills/{created['id']}/versions/1/tool-grants"

    first = await client.post(url, headers=abc.owner_headers, json={"tools": ["read_project"]})
    second = await client.post(url, headers=abc.owner_headers, json={"tools": ["read_project"]})
    assert first.status_code == second.status_code == 200

    audit = await client.get("/audit", headers=abc.owner_headers)
    grants = [entry for entry in audit.json() if entry["event"] == "tool_grant.granted"]
    assert len(grants) == 1
    assert grants[0]["payload"]["tools"] == ["read_project"]
