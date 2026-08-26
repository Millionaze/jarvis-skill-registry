"""Authentication and where tenancy comes from."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_PASSWORD, OrgFixture


async def test_login_returns_a_token_scoped_to_the_users_organization(
    client: AsyncClient, abc: OrgFixture
) -> None:
    response = await client.post(
        "/auth/login", json={"email": abc.owner.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["organization_id"] == str(abc.id)
    assert me.json()["role"] == "owner"


async def test_login_with_a_wrong_password_is_rejected(
    client: AsyncClient, abc: OrgFixture
) -> None:
    response = await client.post(
        "/auth/login", json={"email": abc.owner.email, "password": "not-the-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_unknown_email_is_rejected_with_the_same_code(client: AsyncClient) -> None:
    """No user enumeration: an unknown address looks exactly like a bad password."""
    response = await client.post(
        "/auth/login", json={"email": "nobody@nowhere.test", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.parametrize(
    "path", ["/skills", "/skills/active", "/audit", "/auth/me"]
)
async def test_endpoints_require_a_token(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_a_garbage_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/skills", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
