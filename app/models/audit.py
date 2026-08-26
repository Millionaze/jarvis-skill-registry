from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_column, uuid_pk


class AuditLog(Base):
    """Append-only. Enforced by trg_audit_log_append_only plus a REVOKE of
    UPDATE/DELETE/TRUNCATE from the application role (see alembic 0002).
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_audit_log_organization_id_skill_id", "organization_id", "skill_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=True
    )
    skill_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("skill_versions.id", ondelete="CASCADE"), nullable=True
    )
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_column()
