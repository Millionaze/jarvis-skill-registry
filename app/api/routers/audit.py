from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import SkillServiceDep
from app.schemas.audit import AuditEntryResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryResponse], summary="Audit log for the caller's org")
async def list_audit(
    service: SkillServiceDep, limit: int = Query(default=200, ge=1, le=500)
) -> list[AuditEntryResponse]:
    entries = await service.list_audit_entries(limit=limit)
    return [AuditEntryResponse.model_validate(entry) for entry in entries]
