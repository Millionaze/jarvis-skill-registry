"""close the TRUNCATE gap on audit_log

Revision ID: 0003_audit_log_truncate_guard
Revises: 0002_db_level_guarantees
Create Date: 2026-08-26

Found by the pre-submission audit.

`trg_audit_log_append_only` is a ROW-level trigger, and PostgreSQL does not fire
row triggers for TRUNCATE. The application role could never do it - TRUNCATE was
never granted to it, and 0002 explicitly revokes it - but the schema owner could
still empty the table in one statement, which made "append-only" true for UPDATE
and DELETE and false for TRUNCATE.

A statement-level BEFORE TRUNCATE trigger closes that. It reuses
audit_log_forbid_mutation(), whose message is already driven by TG_OP.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_audit_log_truncate_guard"
down_revision: Union[str, None] = "0002_db_level_guarantees"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_audit_log_no_truncate
            BEFORE TRUNCATE ON audit_log
            FOR EACH STATEMENT
            EXECUTE FUNCTION audit_log_forbid_mutation();
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log;"))
