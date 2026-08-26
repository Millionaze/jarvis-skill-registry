"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-26

Every tenant-owned table carries organization_id as the canonical ownership key,
including skill_versions and tool_grants where it is denormalised on purpose so
that no query needs a join to be scoped.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_users_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_users_role_valid"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "skills",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_skills_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_skills_created_by_users", ondelete="RESTRICT"
        ),
        # One skill name per organization - names are tenant-local, never global.
        sa.UniqueConstraint("organization_id", "name", name="uq_skills_organization_id_name"),
        sa.CheckConstraint("status IN ('draft', 'active', 'disabled')", name="ck_skills_status_valid"),
    )
    op.create_index("ix_skills_organization_id", "skills", ["organization_id"])
    op.create_index("ix_skills_department", "skills", ["department"])
    op.create_index("ix_skills_organization_id_status", "skills", ["organization_id", "status"])

    op.create_table(
        "skill_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("skill_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("prompt_body", sa.Text(), nullable=False),
        sa.Column("requested_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", UUID, nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", UUID, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_skill_versions"),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_skill_versions_skill_id_skills", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_skill_versions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_skill_versions_created_by_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name="fk_skill_versions_reviewed_by_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["activated_by"], ["users.id"], name="fk_skill_versions_activated_by_users", ondelete="RESTRICT"
        ),
        # Monotonic version numbering per skill.
        sa.UniqueConstraint(
            "skill_id", "version_number", name="uq_skill_versions_skill_id_version_number"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'disabled')",
            name="ck_skill_versions_status_valid",
        ),
        sa.CheckConstraint("version_number >= 1", name="ck_skill_versions_version_number_positive"),
    )
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])
    op.create_index("ix_skill_versions_organization_id", "skill_versions", ["organization_id"])
    op.create_index(
        "ix_skill_versions_organization_id_skill_id",
        "skill_versions",
        ["organization_id", "skill_id"],
    )

    op.create_table(
        "tool_grants",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("skill_version_id", UUID, nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        # Requesting a tool must never auto-grant it.
        sa.Column("granted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("granted_by", UUID, nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tool_grants"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_tool_grants_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["skill_versions.id"],
            name="fk_tool_grants_skill_version_id_skill_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="fk_tool_grants_granted_by_users", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "skill_version_id", "tool_name", name="uq_tool_grants_skill_version_id_tool_name"
        ),
    )
    op.create_index("ix_tool_grants_organization_id", "tool_grants", ["organization_id"])
    op.create_index("ix_tool_grants_skill_version_id", "tool_grants", ["skill_version_id"])
    op.create_index(
        "ix_tool_grants_organization_id_skill_version_id",
        "tool_grants",
        ["organization_id", "skill_version_id"],
    )

    op.create_table(
        "audit_log",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("skill_id", UUID, nullable=True),
        sa.Column("skill_version_id", UUID, nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_log_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_audit_log_actor_user_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_audit_log_skill_id_skills", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["skill_versions.id"],
            name="fk_audit_log_skill_version_id_skill_versions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_audit_log_organization_id", "audit_log", ["organization_id"])
    op.create_index("ix_audit_log_event", "audit_log", ["event"])
    op.create_index(
        "ix_audit_log_organization_id_created_at", "audit_log", ["organization_id", "created_at"]
    )
    op.create_index(
        "ix_audit_log_organization_id_skill_id", "audit_log", ["organization_id", "skill_id"]
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("tool_grants")
    op.drop_table("skill_versions")
    op.drop_table("skills")
    op.drop_table("users")
    op.drop_table("organizations")
