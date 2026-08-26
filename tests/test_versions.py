"""Version creation, numbering and hashing."""

from __future__ import annotations

from httpx import AsyncClient

from app.services.hashing import hash_version
from tests import flows
from tests.conftest import OrgFixture


async def test_version_numbers_are_monotonic_per_skill(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    skill_id = created["id"]

    numbers = [created["versions"][0]["version_number"]]
    for index in range(2, 5):
        version = await flows.create_version(
            client, abc.owner_headers, skill_id, prompt_body=f"prompt {index}"
        )
        numbers.append(version["version_number"])

    assert numbers == [1, 2, 3, 4]


async def test_version_numbering_is_independent_per_skill(
    client: AsyncClient, abc: OrgFixture
) -> None:
    first = await flows.create_skill(client, abc.owner_headers, name="First")
    second = await flows.create_skill(client, abc.owner_headers, name="Second")

    await flows.create_version(client, abc.owner_headers, first["id"])
    other = await flows.create_version(client, abc.owner_headers, second["id"])

    assert other["version_number"] == 2


async def test_the_content_hash_covers_the_canonical_payload(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(
        client,
        abc.owner_headers,
        prompt_body="A stable prompt.",
        requested_tools=["read_project", "query_schedule"],
    )
    version = created["versions"][0]

    expected = hash_version(
        organization_id=abc.id,
        skill_id=created["id"],
        version_number=1,
        prompt_body="A stable prompt.",
        requested_tools=["read_project", "query_schedule"],
    )
    assert version["content_hash"] == expected
    assert len(version["content_hash"]) == 64


async def test_requested_tools_are_canonicalised_and_deduplicated(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(
        client,
        abc.owner_headers,
        requested_tools=["read_project", "READ_PROJECT", "query_schedule", "read_project"],
    )
    version = created["versions"][0]
    assert version["requested_tools"] == ["query_schedule", "read_project"]
    assert len(version["tool_grants"]) == 2


async def test_the_same_content_in_different_organizations_hashes_differently(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """The tenant is part of a version's identity."""
    a = await flows.create_skill(client, abc.owner_headers, name="Same", prompt_body="identical")
    b = await flows.create_skill(client, xyz.owner_headers, name="Same", prompt_body="identical")
    assert a["versions"][0]["content_hash"] != b["versions"][0]["content_hash"]


async def test_a_reviewed_version_cannot_be_reviewed_twice(
    client: AsyncClient, abc: OrgFixture
) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    await flows.review(client, abc.owner_headers, created["id"], 1)

    response = await client.post(
        f"/skills/{created['id']}/versions/1/review", headers=abc.owner_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_ALREADY_REVIEWED"


async def test_review_records_who_reviewed_and_when(client: AsyncClient, abc: OrgFixture) -> None:
    created = await flows.create_skill(client, abc.owner_headers)
    reviewed = await flows.review(client, abc.member_headers, created["id"], 1)

    assert reviewed["reviewed_by"] == str(abc.member.id)
    assert reviewed["reviewed_at"] is not None
    assert reviewed["status"] == "draft"  # review is a gate, not an activation
