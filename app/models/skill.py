from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SkillStatus, VersionStatus
from app.db.base import Base, created_at_column, utcnow, uuid_pk


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_skills_organization_id_name"),
        CheckConstraint("status IN ('draft', 'active', 'disabled')", name="status_valid"),
        Index("ix_skills_organization_id_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SkillStatus.DRAFT.value
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
    )

    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill",
        order_by="SkillVersion.version_number",
        cascade="all, delete-orphan",
    )


class SkillVersion(Base):
    """An immutable snapshot of a skill's prompt and requested tools.

    Immutability of an ACTIVE version is defended in three layers:
      1. schema/API  - no route mutates version content; edits create version N+1
      2. application - app.models.events guards before_update
      3. database    - trg_skill_versions_immutable_active (see alembic 0002)
    """

    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint(
            "skill_id", "version_number", name="uq_skill_versions_skill_id_version_number"
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'disabled')", name="status_valid"
        ),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        Index("ix_skill_versions_organization_id_skill_id", "organization_id", "skill_id"),
    )

    #: Columns that may never change once the row is active. Kept in Python and
    #: mirrored in the PL/pgSQL trigger so both layers agree on the definition.
    CONTENT_COLUMNS = ("prompt_body", "requested_tools", "content_hash", "version_number")

    id: Mapped[uuid.UUID] = uuid_pk()
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalised from skills.organization_id for defence in depth: every query
    # can be scoped without a join, and the DB can be audited per-tenant.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_body: Mapped[str] = mapped_column(Text, nullable=False)
    requested_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VersionStatus.DRAFT.value
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    skill: Mapped["Skill"] = relationship(back_populates="versions")
    tool_grants: Mapped[list["ToolGrant"]] = relationship(
        back_populates="skill_version", cascade="all, delete-orphan", order_by="ToolGrant.tool_name"
    )

    @property
    def is_reviewed(self) -> bool:
        return self.reviewed_at is not None and self.reviewed_by is not None


class ToolGrant(Base):
    """A requested tool. `granted` defaults to FALSE - requesting never grants."""

    __tablename__ = "tool_grants"
    __table_args__ = (
        UniqueConstraint(
            "skill_version_id", "tool_name", name="uq_tool_grants_skill_version_id_tool_name"
        ),
        Index("ix_tool_grants_organization_id_skill_version_id", "organization_id", "skill_version_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("skill_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    skill_version: Mapped["SkillVersion"] = relationship(back_populates="tool_grants")
