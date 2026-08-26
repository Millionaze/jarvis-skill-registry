"""Canonical version payload and its content hash.

The hash covers everything that makes a version *what it is*: the tenant, the
skill, the ordinal, the prompt and the requested tool set. It does not cover
lifecycle metadata (status, timestamps, actors), which legitimately changes as
the version is reviewed, activated and superseded.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def canonical_version_payload(
    *,
    organization_id: uuid.UUID,
    skill_id: uuid.UUID,
    version_number: int,
    prompt_body: str,
    requested_tools: list[str],
) -> dict[str, Any]:
    return {
        "organization_id": str(organization_id),
        "skill_id": str(skill_id),
        "version_number": int(version_number),
        "prompt_body": prompt_body,
        "requested_tools": sorted(requested_tools),
    }


def content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_version(
    *,
    organization_id: uuid.UUID,
    skill_id: uuid.UUID,
    version_number: int,
    prompt_body: str,
    requested_tools: list[str],
) -> str:
    return content_hash(
        canonical_version_payload(
            organization_id=organization_id,
            skill_id=skill_id,
            version_number=version_number,
            prompt_body=prompt_body,
            requested_tools=requested_tools,
        )
    )
