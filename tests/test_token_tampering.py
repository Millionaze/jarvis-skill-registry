"""What a caller can and cannot do by shaping their own token.

The organization is a signed claim, but a valid signature is not enough: the
(user, organization) pairing is re-checked against the database on every
request, so a token cannot assert a tenancy the user does not have.
"""

from __future__ import annotations

import uuid

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token
from tests import flows
from tests.conftest import OrgFixture


def _sign(claims: dict) -> str:
    settings = get_settings()
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def test_a_token_claiming_another_organization_is_rejected(
    client: AsyncClient, abc: OrgFixture, xyz: OrgFixture
) -> None:
    """A correctly signed token that pairs ABC's owner with XYZ's org id fails.

    This is the attack the database re-check exists for: without it, anyone able
    to mint a token would inherit another tenant's data.
    """
    forged = create_access_token(user_id=abc.owner.id, organization_id=xyz.id, role="owner")

    response = await client.get("/skills", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_a_token_for_an_unknown_user_is_rejected(
    client: AsyncClient, abc: OrgFixture
) -> None:
    forged = create_access_token(
        user_id=uuid.uuid4(), organization_id=abc.id, role="owner"
    )
    response = await client.get("/skills", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_a_self_promoted_role_claim_does_not_grant_owner_powers(
    client: AsyncClient, abc: OrgFixture
) -> None:
    """Role is read from the database, not from the token."""
    forged = create_access_token(
        user_id=abc.member.id, organization_id=abc.id, role="owner"
    )
    headers = {"Authorization": f"Bearer {forged}"}

    created = await flows.create_skill(client, headers)
    await flows.review(client, headers, created["id"], 1)

    response = await flows.activate(client, headers, created["id"], 1)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_ORG_OWNER"
    assert response.json()["error"]["detail"]["actor_role"] == "member"


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "not-a-uuid", "org": str(uuid.uuid4())},
        {"sub": str(uuid.uuid4()), "org": "not-a-uuid"},
    ],
    ids=["bad-sub", "bad-org"],
)
async def test_malformed_uuid_claims_are_rejected(client: AsyncClient, claims: dict) -> None:
    response = await client.get("/skills", headers={"Authorization": f"Bearer {_sign(claims)}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize(
    "claims",
    [{"sub": str(uuid.uuid4())}, {"org": str(uuid.uuid4())}, {}],
    ids=["no-org", "no-sub", "empty"],
)
def test_a_token_missing_required_claims_is_rejected(claims: dict) -> None:
    with pytest.raises(Exception, match="missing required claims"):
        decode_access_token(_sign(claims))


async def test_a_token_signed_with_the_wrong_secret_is_rejected(
    client: AsyncClient, abc: OrgFixture
) -> None:
    forged = jwt.encode(
        {"sub": str(abc.owner.id), "org": str(abc.id), "role": "owner"},
        "a-different-secret",
        algorithm="HS256",
    )
    response = await client.get("/skills", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_an_expired_token_is_rejected(client: AsyncClient, abc: OrgFixture) -> None:
    expired = _sign(
        {
            "sub": str(abc.owner.id),
            "org": str(abc.id),
            "role": "owner",
            "iat": 1_600_000_000,
            "exp": 1_600_003_600,
        }
    )
    response = await client.get("/skills", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
