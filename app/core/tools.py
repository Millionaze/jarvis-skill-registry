"""Tool allowlist.

Requesting a tool is a *request*, never a grant. This module only decides
whether a tool name may be recorded at all; app.services.tool_grants decides
whether it is ever switched on.
"""

from __future__ import annotations

import re

from app.core.errors import ErrorCode, UnprocessableError

#: The complete set of tool names a skill version may request.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "read_project",
        "read_invoice",
        "send_notification",
        "summarise_document",
        "query_schedule",
    }
)

#: Names that are refused with a distinct code even though they would also fail
#: the allowlist. Being explicit makes the intent auditable and the error useful.
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "shell_exec",
        "exec",
        "eval",
        "drop_table",
        "drop_database",
        "truncate_table",
        "delete_all",
        "sudo",
        "rm",
        "rmdir",
        "chmod",
        "curl",
        "wget",
        "write_file",
        "http_request",
    }
)

#: Shapes that are refused outright: wildcards, path traversal, separators,
#: whitespace, quoting and shell metacharacters.
_FORBIDDEN_SHAPES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[*?]"), "wildcard"),
    (re.compile(r"\.\."), "path traversal"),
    (re.compile(r"[/\\]"), "path separator"),
    (re.compile(r"\s"), "whitespace"),
    (re.compile(r"[;|&`$<>(){}\[\]'\"]"), "shell metacharacter"),
)

#: A well-formed tool name, before any allowlist check.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def validate_requested_tools(tool_names: list[str]) -> list[str]:
    """Validate and canonicalise a requested tool list.

    Returns the de-duplicated, sorted list. Raises UnprocessableError (422) with
    FORBIDDEN_TOOL_PATTERN for destructive/malformed names and UNKNOWN_TOOL for
    names that are merely not on the allowlist.
    """
    canonical: list[str] = []
    for raw in tool_names:
        name = raw.strip() if isinstance(raw, str) else raw
        if not isinstance(name, str) or not name:
            raise UnprocessableError(
                "Tool names must be non-empty strings.",
                code=ErrorCode.FORBIDDEN_TOOL_PATTERN,
                detail={"tool": raw, "reason": "empty or non-string"},
            )

        for pattern, reason in _FORBIDDEN_SHAPES:
            if pattern.search(name):
                raise UnprocessableError(
                    f"Tool name {name!r} is rejected: {reason} is not permitted.",
                    code=ErrorCode.FORBIDDEN_TOOL_PATTERN,
                    detail={"tool": name, "reason": reason},
                )

        lowered = name.lower()
        if lowered in DESTRUCTIVE_TOOLS:
            raise UnprocessableError(
                f"Tool name {name!r} is rejected: destructive capability.",
                code=ErrorCode.FORBIDDEN_TOOL_PATTERN,
                detail={"tool": name, "reason": "destructive capability"},
            )

        if not _NAME_RE.match(lowered):
            raise UnprocessableError(
                f"Tool name {name!r} is not a well-formed tool identifier.",
                code=ErrorCode.FORBIDDEN_TOOL_PATTERN,
                detail={"tool": name, "reason": "malformed identifier"},
            )

        if lowered not in ALLOWED_TOOLS:
            raise UnprocessableError(
                f"Tool {name!r} is not on the allowlist.",
                code=ErrorCode.UNKNOWN_TOOL,
                detail={"tool": name, "allowed_tools": sorted(ALLOWED_TOOLS)},
            )

        if lowered not in canonical:
            canonical.append(lowered)

    return sorted(canonical)
