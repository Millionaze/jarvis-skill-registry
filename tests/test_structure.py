"""Structural guarantees.

These tests assert properties of the codebase itself, so the isolation model
cannot quietly erode. A future contributor who scatters an ad-hoc query, adds an
`organization_id` request field, or introduces an admin role breaks CI here
rather than in production.
"""

from __future__ import annotations

import pathlib

import pytest

from app.core.enums import UserRole
from app.db.base import Base
from app.main import create_app

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICES = sorted((ROOT / "app" / "services").glob("*.py"))
ROUTERS = sorted((ROOT / "app" / "api" / "routers").glob("*.py"))

#: Tables that hold tenant data and must therefore carry organization_id.
TENANT_TABLES = {"users", "skills", "skill_versions", "tool_grants", "audit_log"}


def test_the_services_package_is_not_empty() -> None:
    assert len(SERVICES) >= 4


@pytest.mark.parametrize("path", SERVICES, ids=lambda p: p.name)
def test_no_service_builds_an_unscoped_query(path: pathlib.Path) -> None:
    """Services may only reach the database through the scoped repository.

    They have no way to express an unfiltered query, which is what makes
    "every query filters by organization_id" structural rather than aspirational.
    """
    source = path.read_text()
    for forbidden in (
        "from sqlalchemy import select",
        "sqlalchemy.select",
        "session.execute",
        "session.add(",
        "sessionmaker",
        "create_async_engine",
    ):
        assert forbidden not in source, f"{path.name} uses {forbidden!r}"


@pytest.mark.parametrize("path", ROUTERS, ids=lambda p: p.name)
def test_no_router_reads_an_organization_id_from_the_request(path: pathlib.Path) -> None:
    source = path.read_text()
    assert "organization_id:" not in source, f"{path.name} declares an organization_id parameter"


def test_no_request_schema_accepts_an_organization_id() -> None:
    """Checked against the generated OpenAPI document, so it covers every route."""
    schema = create_app().openapi()

    for name, definition in schema.get("components", {}).get("schemas", {}).items():
        if not name.endswith(("Request",)):
            continue
        assert "organization_id" not in definition.get("properties", {}), (
            f"request schema {name} exposes organization_id"
        )

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            for parameter in operation.get("parameters", []):
                assert parameter["name"] != "organization_id", (
                    f"{method.upper()} {path} takes an organization_id parameter"
                )


def test_there_is_no_cross_tenant_escape_hatch() -> None:
    """No admin role, no superuser, no list-all endpoint."""
    assert {role.value for role in UserRole} == {"owner", "member"}

    schema = create_app().openapi()
    paths = set(schema["paths"])
    for suspicious in ("/admin", "/skills/all", "/organizations", "/internal", "/debug"):
        assert not any(path.startswith(suspicious) for path in paths), (
            f"an endpoint under {suspicious} exists"
        )

    source = "\n".join(path.read_text() for path in ROUTERS + SERVICES)
    for word in ("superuser", "is_admin", "bypass_tenant", "all_organizations"):
        assert word not in source, f"found {word!r} in the application"


@pytest.mark.parametrize("table_name", sorted(TENANT_TABLES))
def test_every_tenant_table_carries_organization_id(table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    assert "organization_id" in table.c, f"{table_name} has no organization_id"
    assert not table.c.organization_id.nullable, f"{table_name}.organization_id is nullable"


def test_skill_versions_and_tool_grants_denormalise_organization_id() -> None:
    """Defence in depth: these could be scoped through a join, and are not."""
    for table_name in ("skill_versions", "tool_grants"):
        table = Base.metadata.tables[table_name]
        assert "organization_id" in table.c
        assert any(
            fk.column.table.name == "organizations" for fk in table.c.organization_id.foreign_keys
        )
