"""Application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401  - registers mappers and the immutability guard
from app.api.errors import register_exception_handlers
from app.api.routers import audit, auth, skills
from app.core.config import get_settings
from app.db.session import dispose_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail fast if JWT_SECRET or a database url is missing
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Jarvis Skill Registry",
        version="1.0.0",
        summary="Organization-scoped registry for AI COO skills.",
        description=(
            "Multi-tenant skill registry. Tenancy is derived exclusively from the "
            "authenticated token; cross-organization reads and writes return 404."
        ),
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(auth.router)
    application.include_router(skills.router)
    application.include_router(audit.router)

    @application.get("/health", tags=["meta"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
