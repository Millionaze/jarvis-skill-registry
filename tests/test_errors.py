"""The error envelope and validation behaviour.

Covers mandatory test 13.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests import flows
from tests.conftest import OrgFixture


def assert_envelope(payload: dict) -> dict:
    """Every error response has exactly one shape."""
    assert set(payload) == {"error"}, payload
    error = payload["error"]
    assert set(error) == {"code", "message", "detail"}, error
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["detail"], dict)
    return error


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"department": "ops", "prompt_body": "p", "requested_tools": []}, "missing name"),
        ({"name": "n", "prompt_body": "p", "requested_tools": []}, "missing department"),
        ({"name": "n", "department": "ops", "requested_tools": []}, "missing prompt_body"),
        ({"name": "", "department": "ops", "prompt_body": "p", "requested_tools": []}, "empty name"),
        (
            {"name": "n", "department": "ops", "prompt_body": "p", "requested_tools": "not-a-list"},
            "wrong type",
        ),
        (
            {"name": "n", "department": "ops", "prompt_body": "p", "requested_tools": [], "x": 1},
            "unmodelled field",
        ),
    ],
)
async def test_validation_failures_return_422_with_the_validation_error_code(
    client: AsyncClient, abc: OrgFixture, body: dict, reason: str
) -> None:
    """Mandatory test 13."""
    response = await client.post("/skills", headers=abc.owner_headers, json=body)
    assert response.status_code == 422, f"{reason}: {response.text}"

    error = assert_envelope(response.json())
    assert error["code"] == "VALIDATION_ERROR"
    assert error["detail"]["errors"], error
    assert "location" in error["detail"]["errors"][0]


async def test_a_malformed_uuid_in_the_path_is_a_422(
    client: AsyncClient, abc: OrgFixture
) -> None:
    response = await client.get("/skills/not-a-uuid", headers=abc.owner_headers)
    assert response.status_code == 422
    assert assert_envelope(response.json())["code"] == "VALIDATION_ERROR"


async def test_an_out_of_range_query_parameter_is_a_422(
    client: AsyncClient, abc: OrgFixture
) -> None:
    response = await client.get("/audit", headers=abc.owner_headers, params={"limit": 10_000})
    assert response.status_code == 422
    assert assert_envelope(response.json())["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("status", "code", "make_request"),
    [
        (404, "SKILL_NOT_FOUND", "missing_skill"),
        (401, "AUTH_REQUIRED", "no_token"),
        (409, "VERSION_NOT_REVIEWED", "activate_unreviewed"),
        (422, "UNKNOWN_TOOL", "unknown_tool"),
    ],
)
async def test_every_error_uses_the_same_envelope(
    client: AsyncClient, abc: OrgFixture, status: int, code: str, make_request: str
) -> None:
    if make_request == "missing_skill":
        response = await client.get(
            "/skills/00000000-0000-0000-0000-000000000000", headers=abc.owner_headers
        )
    elif make_request == "no_token":
        response = await client.get("/skills")
    elif make_request == "activate_unreviewed":
        created = await flows.create_skill(client, abc.owner_headers)
        response = await flows.activate(client, abc.owner_headers, created["id"], 1)
    else:
        response = await client.post(
            "/skills",
            headers=abc.owner_headers,
            json={
                "name": "n",
                "department": "ops",
                "prompt_body": "p",
                "requested_tools": ["not_a_real_tool"],
            },
        )

    assert response.status_code == status, response.text
    assert assert_envelope(response.json())["code"] == code


async def test_error_responses_never_leak_internals(
    client: AsyncClient, abc: OrgFixture
) -> None:
    response = await client.get(
        "/skills/00000000-0000-0000-0000-000000000000", headers=abc.owner_headers
    )
    body = response.text.lower()
    for leak in ("traceback", "sqlalchemy", "asyncpg", "select ", "psycopg", 'file "'):
        assert leak not in body, f"response leaked {leak!r}: {response.text}"
