from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID
    event: str
    skill_id: uuid.UUID | None = None
    skill_version_id: uuid.UUID | None = None
    version_number: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
