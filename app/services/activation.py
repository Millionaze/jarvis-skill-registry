"""Activation.

Rules enforced here:

* only an owner of the OWNING organization may activate (member -> 403,
  another organization's owner -> 404, because the resource is never resolved);
* a version must have been reviewed first - there is no code path anywhere that
  activates automatically;
* activation is idempotent - re-activating the already-active version returns
  200 with unchanged state and writes NO audit row;
* switching versions supersedes the incumbent and activates the successor in a
  single transaction, serialised by a row lock on the skill and backstopped by
  the partial unique index uq_skill_versions_one_active_per_skill.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.enums import AuditEvent, SkillStatus, VersionStatus
from app.core.errors import ConflictError, ErrorCode
from app.models.skill import SkillVersion
from app.services.skills import SkillService


@dataclass(slots=True)
class ActivationResult:
    version: SkillVersion
    changed: bool  #: False when the call was a no-op re-activation


class ActivationService:
    def __init__(self, skills: SkillService) -> None:
        self._skills = skills
        self._repo = skills._repo  # noqa: SLF001 - same package, one unit of work
        self._audit = skills._audit  # noqa: SLF001

    async def activate(self, skill_id: uuid.UUID, version_number: int) -> ActivationResult:
        # 1. resolve inside the tenant scope (and serialise concurrent activations)
        skill = await self._skills._lock_skill(skill_id)  # noqa: SLF001
        version = await self._skills._require_version(skill_id, version_number)  # noqa: SLF001

        # 2. role check happens only once the resource is proven visible
        self._skills._require_owner("activate a version")  # noqa: SLF001

        # 3. idempotency: already active -> unchanged state, no audit row
        if version.status == VersionStatus.ACTIVE.value:
            return ActivationResult(version=version, changed=False)

        # 4. state rules
        if skill.status == SkillStatus.DISABLED.value:
            raise ConflictError(
                "Skill is disabled and cannot have versions activated.",
                code=ErrorCode.SKILL_DISABLED,
                detail={"skill_id": str(skill_id)},
            )
        if version.status != VersionStatus.DRAFT.value:
            raise ConflictError(
                f"A {version.status!r} version cannot be activated.",
                code=ErrorCode.VERSION_NOT_ACTIVATABLE,
                detail={"version_number": version_number, "status": version.status},
            )
        if not version.is_reviewed:
            raise ConflictError(
                "Version must be reviewed before it can be activated.",
                code=ErrorCode.VERSION_NOT_REVIEWED,
                detail={"version_number": version_number},
            )

        now = datetime.now(UTC)

        # 5. supersede the incumbent first, and flush, so the partial unique
        #    index never sees two active rows for this skill.
        incumbent = await self._repo.get_active_version(skill_id)
        if incumbent is not None and incumbent.id != version.id:
            incumbent.status = VersionStatus.SUPERSEDED.value
            await self._repo.flush()
            self._audit.record(
                AuditEvent.VERSION_SUPERSEDED,
                skill=skill,
                version=incumbent,
                payload={"superseded_by_version_number": version.version_number},
            )

        version.status = VersionStatus.ACTIVE.value
        version.activated_at = now
        version.activated_by = self._skills._actor.id  # noqa: SLF001
        skill.status = SkillStatus.ACTIVE.value

        self._audit.record(
            AuditEvent.VERSION_ACTIVATED,
            skill=skill,
            version=version,
            payload={
                "content_hash": version.content_hash,
                "previous_active_version_number": (
                    incumbent.version_number if incumbent is not None else None
                ),
            },
        )
        await self._repo.commit()

        refreshed = await self._skills._require_version(skill_id, version_number)  # noqa: SLF001
        return ActivationResult(version=refreshed, changed=True)
