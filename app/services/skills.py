"""Skill lifecycle: draft -> version -> review -> (owner) activate -> supersede.

Authorisation order in this module is deliberate and load-bearing:

    1. resolve the resource through the org-scoped repository  -> 404 if invisible
    2. only then check the caller's role                       -> 403 if wrong role
    3. only then check state                                   -> 409

Doing role checks first would let a caller from another organization distinguish
"exists but you are not the owner" from "does not exist". See ARCHITECTURE.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.enums import AuditEvent, SkillStatus, VersionStatus
from app.core.errors import (
    ConflictError,
    ErrorCode,
    PermissionDeniedError,
    ResourceNotFoundError,
    UnprocessableError,
)
from sqlalchemy.exc import IntegrityError

from app.core.tools import validate_requested_tools
from app.db.repository import SkillRepository
from app.models.audit import AuditLog
from app.models.skill import Skill, SkillVersion, ToolGrant
from app.models.user import User
from app.schemas.skill import (
    SkillCreateRequest,
    SkillUpdateRequest,
    ToolGrantRequest,
    VersionCreateRequest,
)
from app.services.audit import AuditRecorder
from app.services.hashing import hash_version


class SkillService:
    def __init__(self, repo: SkillRepository, actor: User) -> None:
        self._repo = repo
        self._actor = actor
        self._audit = AuditRecorder(repo, actor)

    # -- guards ------------------------------------------------------------

    def _require_owner(self, action: str) -> None:
        """403 only after the resource has been proven visible to this tenant."""
        if not self._actor.is_owner:
            raise PermissionDeniedError(
                f"Only an organization owner may {action}.",
                code=ErrorCode.NOT_ORG_OWNER,
                detail={"required_role": "owner", "actor_role": self._actor.role},
            )

    async def _require_skill(self, skill_id: uuid.UUID) -> Skill:
        return await self._repo.require(
            Skill, skill_id, code=ErrorCode.SKILL_NOT_FOUND, message="Skill not found."
        )

    async def _lock_skill(self, skill_id: uuid.UUID) -> Skill:
        skill = await self._repo.lock_skill(skill_id)
        if skill is None:
            raise ResourceNotFoundError(
                "Skill not found.",
                code=ErrorCode.SKILL_NOT_FOUND,
                detail={"skill_id": str(skill_id)},
            )
        return skill

    async def _require_version(self, skill_id: uuid.UUID, version_number: int) -> SkillVersion:
        version = await self._repo.get_version(skill_id, version_number)
        if version is None:
            raise ResourceNotFoundError(
                "Skill version not found.",
                code=ErrorCode.SKILL_VERSION_NOT_FOUND,
                detail={"skill_id": str(skill_id), "version_number": version_number},
            )
        return version

    # -- reads -------------------------------------------------------------

    async def list_skills(self) -> list[Skill]:
        return await self._repo.list_skills()

    async def get_skill_detail(self, skill_id: uuid.UUID) -> Skill:
        skill = await self._repo.get_skill_with_versions(skill_id)
        if skill is None:
            raise ResourceNotFoundError(
                "Skill not found.",
                code=ErrorCode.SKILL_NOT_FOUND,
                detail={"skill_id": str(skill_id)},
            )
        return skill

    async def list_audit_entries(self, limit: int = 500) -> list[AuditLog]:
        return await self._audit.list_entries(limit=limit)

    async def active_skills(self, department: str | None = None) -> list[tuple[Skill, SkillVersion]]:
        """Runtime selection. Drafts, disabled skills and non-active versions can
        never appear here - the query filters on both statuses."""
        return await self._repo.active_skill_versions(department=department)

    # -- writes ------------------------------------------------------------

    async def create_skill(self, payload: SkillCreateRequest) -> Skill:
        existing = await self._repo.find_skill_by_name(payload.name)
        if existing is not None:
            raise ConflictError(
                f"A skill named {payload.name!r} already exists in this organization.",
                code=ErrorCode.SKILL_NAME_CONFLICT,
                detail={"name": payload.name},
            )

        tools = validate_requested_tools(payload.requested_tools)

        skill = self._repo.add(
            Skill(
                name=payload.name,
                department=payload.department,
                description=payload.description,
                status=SkillStatus.DRAFT.value,
                created_by=self._actor.id,
            )
        )

        # The check above is a fast path that produces a good error message; it is
        # not the guarantee. Two concurrent creates can both pass it, so the
        # authority is uq_skills_organization_id_name and we translate its
        # violation into the same 409 rather than letting it become a 500.
        try:
            await self._repo.flush()
        except IntegrityError as exc:
            await self._repo.rollback()
            if "uq_skills_organization_id_name" in str(exc.orig):
                raise ConflictError(
                    f"A skill named {payload.name!r} already exists in this organization.",
                    code=ErrorCode.SKILL_NAME_CONFLICT,
                    detail={"name": payload.name},
                ) from exc
            raise

        version = await self._create_version_row(
            skill=skill, version_number=1, prompt_body=payload.prompt_body, tools=tools
        )

        self._audit.record(
            AuditEvent.SKILL_CREATED,
            skill=skill,
            payload={"name": skill.name, "department": skill.department},
        )
        self._audit.record(
            AuditEvent.VERSION_CREATED,
            skill=skill,
            version=version,
            payload={"requested_tools": tools, "content_hash": version.content_hash},
        )
        await self._repo.commit()
        return await self.get_skill_detail(skill.id)

    async def update_skill(self, skill_id: uuid.UUID, payload: SkillUpdateRequest) -> Skill:
        """Skill-level metadata only. There is no route anywhere that edits the
        content of a version - that is layer 1 of the immutability defence."""
        skill = await self._require_skill(skill_id)
        if skill.status == SkillStatus.DISABLED.value:
            raise ConflictError(
                "Skill is disabled.", code=ErrorCode.SKILL_DISABLED, detail={"skill_id": str(skill_id)}
            )

        changes: dict[str, str] = {}
        if payload.department is not None:
            skill.department = payload.department
            changes["department"] = payload.department
        if payload.description is not None:
            skill.description = payload.description
            changes["description"] = payload.description

        if changes:
            self._audit.record(AuditEvent.SKILL_UPDATED, skill=skill, payload={"changes": changes})
        await self._repo.commit()
        return await self.get_skill_detail(skill.id)

    async def create_version(
        self, skill_id: uuid.UUID, payload: VersionCreateRequest
    ) -> SkillVersion:
        """Editing an active skill means adding version N+1; nothing is mutated."""
        skill = await self._lock_skill(skill_id)
        if skill.status == SkillStatus.DISABLED.value:
            raise ConflictError(
                "Skill is disabled.", code=ErrorCode.SKILL_DISABLED, detail={"skill_id": str(skill_id)}
            )

        tools = validate_requested_tools(payload.requested_tools)
        next_number = await self._repo.next_version_number(skill_id)
        version = await self._create_version_row(
            skill=skill, version_number=next_number, prompt_body=payload.prompt_body, tools=tools
        )
        self._audit.record(
            AuditEvent.VERSION_CREATED,
            skill=skill,
            version=version,
            payload={"requested_tools": tools, "content_hash": version.content_hash},
        )
        await self._repo.commit()
        return await self._require_version(skill_id, next_number)

    async def _create_version_row(
        self, *, skill: Skill, version_number: int, prompt_body: str, tools: list[str]
    ) -> SkillVersion:
        version = self._repo.add(
            SkillVersion(
                skill_id=skill.id,
                version_number=version_number,
                prompt_body=prompt_body,
                requested_tools=tools,
                status=VersionStatus.DRAFT.value,
                content_hash=hash_version(
                    organization_id=self._repo.organization_id,
                    skill_id=skill.id,
                    version_number=version_number,
                    prompt_body=prompt_body,
                    requested_tools=tools,
                ),
                created_by=self._actor.id,
            )
        )
        await self._repo.flush()

        # Requesting a tool records an ungranted request. It never grants.
        for tool_name in tools:
            self._repo.add(
                ToolGrant(skill_version_id=version.id, tool_name=tool_name, granted=False)
            )
        await self._repo.flush()
        return version

    async def review_version(self, skill_id: uuid.UUID, version_number: int) -> SkillVersion:
        version = await self._require_version(skill_id, version_number)

        if version.status == VersionStatus.ACTIVE.value:
            raise ConflictError(
                "An active version is immutable and cannot be re-reviewed.",
                code=ErrorCode.ACTIVE_VERSION_IMMUTABLE,
                detail={"version_number": version_number, "status": version.status},
            )
        if version.status != VersionStatus.DRAFT.value:
            raise ConflictError(
                f"Only a draft version can be reviewed (this one is {version.status!r}).",
                code=ErrorCode.VERSION_NOT_ACTIVATABLE,
                detail={"version_number": version_number, "status": version.status},
            )
        if version.is_reviewed:
            raise ConflictError(
                "Version has already been reviewed.",
                code=ErrorCode.VERSION_ALREADY_REVIEWED,
                detail={"version_number": version_number},
            )

        version.reviewed_at = datetime.now(UTC)
        version.reviewed_by = self._actor.id
        self._audit.record(
            AuditEvent.VERSION_REVIEWED,
            version=version,
            payload={"reviewed_by": str(self._actor.id)},
        )
        await self._repo.commit()
        return await self._require_version(skill_id, version_number)

    async def grant_tools(
        self, skill_id: uuid.UUID, version_number: int, payload: ToolGrantRequest
    ) -> SkillVersion:
        """Granting is a separate, explicit, owner-only act."""
        version = await self._require_version(skill_id, version_number)
        self._require_owner("grant tools")

        requested = validate_requested_tools(payload.tools)
        by_name = {grant.tool_name: grant for grant in version.tool_grants}

        missing = [name for name in requested if name not in by_name]
        if missing:
            raise UnprocessableError(
                "Cannot grant a tool that this version did not request.",
                code=ErrorCode.TOOL_NOT_REQUESTED,
                detail={"tools": missing, "requested_tools": sorted(by_name)},
            )

        newly_granted: list[str] = []
        now = datetime.now(UTC)
        for name in requested:
            grant = by_name[name]
            if grant.granted:
                continue
            grant.granted = True
            grant.granted_by = self._actor.id
            grant.granted_at = now
            newly_granted.append(name)

        if newly_granted:
            self._audit.record(
                AuditEvent.TOOL_GRANTED,
                version=version,
                payload={"tools": newly_granted, "granted_by": str(self._actor.id)},
            )
        await self._repo.commit()
        return await self._require_version(skill_id, version_number)

    async def disable_skill(self, skill_id: uuid.UUID) -> Skill:
        skill = await self._lock_skill(skill_id)
        self._require_owner("disable a skill")

        if skill.status == SkillStatus.DISABLED.value:
            return await self.get_skill_detail(skill_id)  # idempotent, no duplicate audit

        active_version = await self._repo.get_active_version(skill_id)
        if active_version is not None:
            # active -> disabled is one of the two legal transitions out of active.
            active_version.status = VersionStatus.DISABLED.value
            self._audit.record(AuditEvent.VERSION_DISABLED, skill=skill, version=active_version)

        skill.status = SkillStatus.DISABLED.value
        self._audit.record(AuditEvent.SKILL_DISABLED, skill=skill, payload={"name": skill.name})
        await self._repo.commit()
        return await self.get_skill_detail(skill_id)
