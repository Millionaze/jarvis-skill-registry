"""Application-layer immutability guard - layer 2 of 3.

Layer 1 is the API surface: no route mutates version content; an edit creates
version N+1.
Layer 2 is this listener: any attempt to flush an UPDATE against a row that was
ACTIVE raises before SQL is emitted, whatever code path produced it.
Layer 3 is the PL/pgSQL trigger installed by alembic revision 0002, which also
catches raw SQL that bypasses the ORM entirely.

The only legal update to an active version is a status transition to
'superseded' or 'disabled', with no content change.
"""

from __future__ import annotations

from sqlalchemy import event, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper

from app.core.enums import VersionStatus
from app.core.errors import ImmutableVersionError
from app.models.skill import SkillVersion

LEGAL_TRANSITIONS_FROM_ACTIVE: frozenset[str] = frozenset(
    {VersionStatus.SUPERSEDED.value, VersionStatus.DISABLED.value}
)


@event.listens_for(SkillVersion, "before_update")
def guard_active_version_immutability(
    mapper: Mapper[SkillVersion], connection: Connection, target: SkillVersion
) -> None:
    state = inspect(target)

    status_history = state.attrs.status.history
    previous_status = (
        status_history.deleted[0] if status_history.deleted else target.status
    )

    if previous_status != VersionStatus.ACTIVE.value:
        return  # not an active row: ordinary lifecycle updates are fine

    changed_content = [
        column
        for column in SkillVersion.CONTENT_COLUMNS
        if state.attrs[column].history.has_changes()
    ]
    if changed_content:
        raise ImmutableVersionError(
            "Active skill version content is immutable; create a new version instead. "
            f"Attempted to change: {', '.join(sorted(changed_content))}"
        )

    if status_history.deleted and target.status not in LEGAL_TRANSITIONS_FROM_ACTIVE:
        raise ImmutableVersionError(
            f"Illegal transition from 'active' to {target.status!r}; "
            f"only {sorted(LEGAL_TRANSITIONS_FROM_ACTIVE)} are permitted."
        )
