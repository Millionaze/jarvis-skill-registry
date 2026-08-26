"""Domain enumerations.

Stored as text with CHECK constraints rather than native PG enum types: the
values are compared directly inside PL/pgSQL triggers and are cheap to extend
without an ALTER TYPE dance.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class SkillStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DISABLED = "disabled"


class AuditEvent(StrEnum):
    SKILL_CREATED = "skill.created"
    SKILL_UPDATED = "skill.updated"
    SKILL_DISABLED = "skill.disabled"
    VERSION_CREATED = "skill_version.created"
    VERSION_REVIEWED = "skill_version.reviewed"
    VERSION_ACTIVATED = "skill_version.activated"
    VERSION_SUPERSEDED = "skill_version.superseded"
    VERSION_DISABLED = "skill_version.disabled"
    TOOL_GRANTED = "tool_grant.granted"
