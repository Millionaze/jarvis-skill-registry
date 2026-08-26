"""Audit recording.

Every audit row is added to the *same* unit of work as the state change it
describes and committed with it, so the log and the data can never diverge: if
the state change rolls back, so does its audit row, and vice versa.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import AuditEvent
from app.db.repository import ScopedRepository
from app.models.audit import AuditLog
from app.models.skill import Skill, SkillVersion
from app.models.user import User


class AuditRecorder:
    def __init__(self, repo: ScopedRepository, actor: User) -> None:
        self._repo = repo
        self._actor = actor

    def record(
        self,
        event: AuditEvent,
        *,
        skill: Skill | None = None,
        version: SkillVersion | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_user_id=self._actor.id,
            event=event.value,
            skill_id=skill.id if skill is not None else (version.skill_id if version else None),
            skill_version_id=version.id if version is not None else None,
            version_number=version.version_number if version is not None else None,
            payload=payload or {},
        )
        # repo.add() stamps organization_id from the caller's token, never from input.
        return self._repo.add(entry)

    async def list_entries(self, limit: int = 500) -> list[AuditLog]:
        stmt = (
            self._repo.select(AuditLog)
            .order_by(AuditLog.created_at.desc(), AuditLog.event)
            .limit(limit)
        )
        return await self._repo.scalars(stmt)
