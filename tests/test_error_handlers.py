"""The global exception handlers themselves.

The handlers below are the last line between an internal failure and the
client, so they are tested directly against a throwaway app rather than only
through routes that happen to be well behaved.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.errors import register_exception_handlers
from app.core.errors import DomainError, ErrorCode, ImmutableVersionError
from app.db.session import dispose_engine, get_engine, get_session, get_sessionmaker


@pytest.fixture
def failing_app() -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)

    @application.get("/boom/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret internal detail: connection string postgresql://u:p@h/db")

    @application.get("/boom/immutable")
    async def immutable() -> None:
        raise ImmutableVersionError("Active skill version content is immutable.")

    @application.get("/boom/domain")
    async def domain() -> None:
        raise DomainError(
            "Teapot.", code="IM_A_TEAPOT", status_code=418, detail={"hint": "brew"}
        )

    return application


@pytest.fixture
async def failing_client(failing_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=failing_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def test_an_unexpected_error_becomes_an_opaque_500(failing_client: AsyncClient) -> None:
    """No stack trace, no driver message, no connection string."""
    response = await failing_client.get("/boom/unexpected")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": ErrorCode.INTERNAL_ERROR,
            "message": "An unexpected error occurred.",
            "detail": {},
        }
    }
    body = response.text.lower()
    for leak in ("runtimeerror", "traceback", "postgresql://", "secret internal detail"):
        assert leak not in body


async def test_the_application_immutability_guard_surfaces_as_409(
    failing_client: AsyncClient,
) -> None:
    response = await failing_client.get("/boom/immutable")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == ErrorCode.ACTIVE_VERSION_IMMUTABLE
    assert "immutable" in error["message"].lower()


async def test_a_domain_error_can_override_its_status_and_code(
    failing_client: AsyncClient,
) -> None:
    response = await failing_client.get("/boom/domain")

    assert response.status_code == 418
    assert response.json()["error"] == {
        "code": "IM_A_TEAPOT",
        "message": "Teapot.",
        "detail": {"hint": "brew"},
    }


async def test_an_unauthenticated_response_advertises_the_bearer_scheme(
    client: AsyncClient,
) -> None:
    response = await client.get("/skills")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


async def test_the_real_engine_and_sessionmaker_work() -> None:
    """Exercises the production session plumbing, which tests otherwise override."""
    try:
        assert get_engine() is get_engine()  # cached
        async with get_sessionmaker()() as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await dispose_engine()


async def test_the_session_dependency_rolls_back_on_an_escaping_exception() -> None:
    """The request-scoped dependency the app really uses, which tests override."""
    from sqlalchemy.ext.asyncio import AsyncSession

    generator = get_session()
    try:
        session = await generator.__anext__()
        assert isinstance(session, AsyncSession)

        with pytest.raises(RuntimeError, match="handler blew up"):
            await generator.athrow(RuntimeError("handler blew up"))

        assert not session.in_transaction()
    finally:
        await dispose_engine()
