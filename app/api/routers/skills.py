"""Skill routes.

Note what is absent: there is no PUT/PATCH on a version, and no endpoint that
takes an organization id. The tenancy of every call comes from the token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ActivationServiceDep, SkillServiceDep
from app.schemas.skill import (
    ActiveSkillResponse,
    SkillCreateRequest,
    SkillDetailResponse,
    SkillResponse,
    SkillUpdateRequest,
    SkillVersionResponse,
    ToolGrantRequest,
    VersionCreateRequest,
)

router = APIRouter(prefix="/skills", tags=["skills"])


# Registered before /{skill_id} so that "active" is never parsed as an id.
@router.get(
    "/active",
    response_model=list[ActiveSkillResponse],
    summary="Runtime selection: active skills for a department",
)
async def list_active_skills(
    service: SkillServiceDep,
    department: str | None = Query(default=None, max_length=100),
) -> list[ActiveSkillResponse]:
    """Only skills that are active, in the caller's organization, and that have
    an active version. Drafts and disabled skills can never appear here, and
    only *granted* tools are exposed."""
    rows = await service.active_skills(department=department)
    result: list[ActiveSkillResponse] = []
    for skill, version in rows:
        result.append(
            ActiveSkillResponse(
                skill_id=skill.id,
                organization_id=skill.organization_id,
                name=skill.name,
                department=skill.department,
                description=skill.description,
                version_id=version.id,
                version_number=version.version_number,
                prompt_body=version.prompt_body,
                content_hash=version.content_hash,
                granted_tools=[g.tool_name for g in version.tool_grants if g.granted],
                activated_at=version.activated_at,
            )
        )
    return result


@router.post(
    "",
    response_model=SkillDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a skill draft (with version 1)",
)
async def create_skill(payload: SkillCreateRequest, service: SkillServiceDep) -> SkillDetailResponse:
    skill = await service.create_skill(payload)
    return SkillDetailResponse.model_validate(skill)


@router.get("", response_model=list[SkillResponse], summary="List skills for the caller's org")
async def list_skills(service: SkillServiceDep) -> list[SkillResponse]:
    skills = await service.list_skills()
    return [SkillResponse.model_validate(skill) for skill in skills]


@router.get("/{skill_id}", response_model=SkillDetailResponse, summary="Read a skill and versions")
async def get_skill(skill_id: uuid.UUID, service: SkillServiceDep) -> SkillDetailResponse:
    skill = await service.get_skill_detail(skill_id)
    return SkillDetailResponse.model_validate(skill)


@router.patch("/{skill_id}", response_model=SkillDetailResponse, summary="Update skill metadata")
async def update_skill(
    skill_id: uuid.UUID, payload: SkillUpdateRequest, service: SkillServiceDep
) -> SkillDetailResponse:
    skill = await service.update_skill(skill_id, payload)
    return SkillDetailResponse.model_validate(skill)


@router.post(
    "/{skill_id}/versions",
    response_model=SkillVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new immutable version",
)
async def create_version(
    skill_id: uuid.UUID, payload: VersionCreateRequest, service: SkillServiceDep
) -> SkillVersionResponse:
    version = await service.create_version(skill_id, payload)
    return SkillVersionResponse.model_validate(version)


@router.post(
    "/{skill_id}/versions/{version_number}/review",
    response_model=SkillVersionResponse,
    summary="Mark a draft version reviewed",
)
async def review_version(
    skill_id: uuid.UUID, version_number: int, service: SkillServiceDep
) -> SkillVersionResponse:
    version = await service.review_version(skill_id, version_number)
    return SkillVersionResponse.model_validate(version)


@router.post(
    "/{skill_id}/versions/{version_number}/activate",
    response_model=SkillVersionResponse,
    summary="Activate a reviewed version (owner only, idempotent)",
)
async def activate_version(
    skill_id: uuid.UUID,
    version_number: int,
    activation: ActivationServiceDep,
    response: Response,
) -> SkillVersionResponse:
    result = await activation.activate(skill_id, version_number)
    # Idempotent replay is still a 200; the header makes the no-op observable.
    response.headers["X-Activation-Changed"] = "true" if result.changed else "false"
    return SkillVersionResponse.model_validate(result.version)


@router.post(
    "/{skill_id}/versions/{version_number}/tool-grants",
    response_model=SkillVersionResponse,
    summary="Grant requested tools (owner only)",
)
async def grant_tools(
    skill_id: uuid.UUID,
    version_number: int,
    payload: ToolGrantRequest,
    service: SkillServiceDep,
) -> SkillVersionResponse:
    version = await service.grant_tools(skill_id, version_number, payload)
    return SkillVersionResponse.model_validate(version)


@router.post(
    "/{skill_id}/disable", response_model=SkillDetailResponse, summary="Disable a skill (owner only)"
)
async def disable_skill(skill_id: uuid.UUID, service: SkillServiceDep) -> SkillDetailResponse:
    skill = await service.disable_skill(skill_id)
    return SkillDetailResponse.model_validate(skill)
