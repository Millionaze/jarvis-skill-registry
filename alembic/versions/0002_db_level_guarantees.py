"""database-level guarantees: immutability, append-only audit, one active version

Revision ID: 0002_db_level_guarantees
Revises: 0001_initial_schema
Create Date: 2026-08-26

This migration is layer 3 of the immutability defence. It does not trust the
application: the rules below hold for raw SQL, for psql, for a buggy service and
for a compromised process.

  * trg_skill_versions_immutable_active - BEFORE UPDATE on skill_versions raises
    if the row was ACTIVE and any content column changes, if ownership changes,
    or if the status leaves 'active' for anything other than 'superseded' or
    'disabled'.
  * uq_skill_versions_one_active_per_skill - partial unique index guaranteeing at
    most one active version per skill.
  * trg_audit_log_append_only - BEFORE UPDATE OR DELETE on audit_log always
    raises, plus a REVOKE of UPDATE/DELETE/TRUNCATE from the application role.
"""
from __future__ import annotations

import os
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_db_level_guarantees"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _app_role() -> str:
    role = os.environ.get("APP_DB_USER", "jarvis_app")
    if not _IDENTIFIER_RE.match(role):
        raise RuntimeError(f"APP_DB_USER={role!r} is not a valid postgres identifier")
    return role


IMMUTABLE_ACTIVE_FN = """
CREATE OR REPLACE FUNCTION skill_versions_forbid_active_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF OLD.status = 'active' THEN
        IF NEW.prompt_body     IS DISTINCT FROM OLD.prompt_body
        OR NEW.requested_tools IS DISTINCT FROM OLD.requested_tools
        OR NEW.content_hash    IS DISTINCT FROM OLD.content_hash
        OR NEW.version_number  IS DISTINCT FROM OLD.version_number THEN
            RAISE EXCEPTION
                'skill_versions %: the content of an ACTIVE version is immutable; create a new version instead',
                OLD.id
                USING ERRCODE = '23514';
        END IF;

        IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.skill_id        IS DISTINCT FROM OLD.skill_id THEN
            RAISE EXCEPTION
                'skill_versions %: the ownership of an ACTIVE version is immutable', OLD.id
                USING ERRCODE = '23514';
        END IF;

        IF NEW.status NOT IN ('active', 'superseded', 'disabled') THEN
            RAISE EXCEPTION
                'skill_versions %: illegal transition from ACTIVE to %', OLD.id, NEW.status
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$fn$;
"""

APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION audit_log_forbid_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP
        USING ERRCODE = '23514';
END;
$fn$;
"""


def upgrade() -> None:
    role = _app_role()

    op.execute(sa.text(IMMUTABLE_ACTIVE_FN))
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_skill_versions_immutable_active
            BEFORE UPDATE ON skill_versions
            FOR EACH ROW
            EXECUTE FUNCTION skill_versions_forbid_active_mutation();
            """
        )
    )

    # At most one ACTIVE version per skill, enforced by the database.
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_skill_versions_one_active_per_skill
            ON skill_versions (skill_id)
            WHERE status = 'active';
            """
        )
    )

    op.execute(sa.text(APPEND_ONLY_FN))
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_audit_log_append_only
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW
            EXECUTE FUNCTION audit_log_forbid_mutation();
            """
        )
    )

    # Privileges for the restricted application role. Wrapped in a DO block so
    # the migration still applies on a database that has no such role.
    op.execute(
        sa.text(
            f"""
            DO $grants$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'GRANT USAGE ON SCHEMA public TO "{role}"';
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"';
                    -- The audit log is append-only for the application.
                    EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM "{role}"';
                END IF;
            END
            $grants$;
            """
        )
    )


def downgrade() -> None:
    role = _app_role()
    op.execute(
        sa.text(
            f"""
            DO $grants$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"';
                END IF;
            END
            $grants$;
            """
        )
    )
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log;"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS audit_log_forbid_mutation();"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_skill_versions_one_active_per_skill;"))
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_skill_versions_immutable_active ON skill_versions;")
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS skill_versions_forbid_active_mutation();"))
