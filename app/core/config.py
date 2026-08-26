"""Application configuration.

Every value is read from the environment. `jwt_secret` deliberately has no
default: an operator who forgets to set it gets a startup failure rather than a
silently insecure deployment.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "jarvis-skill-registry"

    # Connection used by the API. Points at the restricted application role.
    database_url: str
    # Connection used by Alembic. Points at the owning role (needs DDL + GRANT).
    migration_database_url: str
    # Name of the restricted role, so the migration can target its GRANT/REVOKE.
    app_db_user: str = "jarvis_app"

    # --- auth -------------------------------------------------------------
    jwt_secret: str  # required, no default
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- fixtures ---------------------------------------------------------
    # Suppressing S105 here: not a secret. This is the password given to the development
    # fixture users by app/seed.py, and it is meant to be public - the README
    # prints it. Real deployments override SEED_PASSWORD, and no production
    # credential is ever defaulted here (contrast jwt_secret, which has none).
    seed_password: str = "dev-only-not-a-secret"  # noqa: S105

    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
