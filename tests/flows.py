"""Small helpers that drive the public API, so tests read as workflows."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

DEFAULT_PROMPT = "You are the ABC scheduling assistant. Summarise today's site schedule."


async def create_skill(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str = "Daily Schedule Digest",
    department: str = "operations",
    prompt_body: str = DEFAULT_PROMPT,
    requested_tools: list[str] | None = None,
    description: str = "Summarises the day's schedule for site managers.",
) -> dict[str, Any]:
    response = await client.post(
        "/skills",
        headers=headers,
        json={
            "name": name,
            "department": department,
            "description": description,
            "prompt_body": prompt_body,
            "requested_tools": requested_tools if requested_tools is not None else ["query_schedule"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_version(
    client: AsyncClient,
    headers: dict[str, str],
    skill_id: str,
    *,
    prompt_body: str = "Revised prompt body.",
    requested_tools: list[str] | None = None,
) -> dict[str, Any]:
    response = await client.post(
        f"/skills/{skill_id}/versions",
        headers=headers,
        json={
            "prompt_body": prompt_body,
            "requested_tools": requested_tools if requested_tools is not None else ["read_project"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def review(
    client: AsyncClient, headers: dict[str, str], skill_id: str, version_number: int
) -> dict[str, Any]:
    response = await client.post(
        f"/skills/{skill_id}/versions/{version_number}/review", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def activate(
    client: AsyncClient, headers: dict[str, str], skill_id: str, version_number: int
):
    return await client.post(
        f"/skills/{skill_id}/versions/{version_number}/activate", headers=headers
    )


async def create_reviewed_and_active_skill(
    client: AsyncClient, org, **kwargs: Any
) -> dict[str, Any]:
    """Full happy path: draft -> review -> owner activates."""
    skill = await create_skill(client, org.owner_headers, **kwargs)
    skill_id = skill["id"]
    await review(client, org.owner_headers, skill_id, 1)
    response = await activate(client, org.owner_headers, skill_id, 1)
    assert response.status_code == 200, response.text
    return {"skill": skill, "skill_id": skill_id, "active_version": response.json()}
