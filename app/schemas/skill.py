from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import StrictModel


class SkillCreateRequest(StrictModel):
    """Creates the skill and its first draft version in one call."""

    name: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4000)
    prompt_body: str = Field(min_length=1, max_length=50_000)
    requested_tools: list[str] = Field(default_factory=list, max_length=32)


class SkillUpdateRequest(StrictModel):
    """Skill-level metadata only. Version content is never editable."""

    department: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=4000)


class VersionCreateRequest(StrictModel):
    prompt_body: str = Field(min_length=1, max_length=50_000)
    requested_tools: list[str] = Field(default_factory=list, max_length=32)


class ToolGrantRequest(StrictModel):
    tools: list[str] = Field(min_length=1, max_length=32)


class ToolGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tool_name: str
    granted: bool
    granted_by: uuid.UUID | None = None
    granted_at: datetime | None = None


class SkillVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    organization_id: uuid.UUID
    version_number: int
    prompt_body: str
    requested_tools: list[str]
    status: str
    content_hash: str
    created_by: uuid.UUID
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
    activated_at: datetime | None = None
    activated_by: uuid.UUID | None = None
    tool_grants: list[ToolGrantResponse] = Field(default_factory=list)


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    department: str
    description: str
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SkillDetailResponse(SkillResponse):
    versions: list[SkillVersionResponse] = Field(default_factory=list)


class ActiveSkillResponse(BaseModel):
    """Runtime selection payload. Exposes granted tools only."""

    skill_id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    department: str
    description: str
    version_id: uuid.UUID
    version_number: int
    prompt_body: str
    content_hash: str
    granted_tools: list[str]
    activated_at: datetime | None = None
