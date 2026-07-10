"""Application settings loaded from environment variables / .env.

This is the single source of truth for configuration. Every other module
(db.base, core.security, alembic/env.py) must import `settings` from here
instead of reading os.environ directly.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env (forgehub/.env), two levels up from backend/app/core/.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres connection (shared `company_postgres` instance, see docs/DB_README.md)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "foundation"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "forgehub"
    POSTGRES_SCHEMA: str = "company"

    # Auth
    JWT_SECRET: str = "dev_only_insecure_jwt_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Temporary single hardcoded dev user — placeholder until a real
    # Users/Auth domain exists (out of scope for this foundation step).
    DEV_USER_USERNAME: str = "admin"
    DEV_USER_PASSWORD: str = "admin"

    # Chat bridge (host-bridge/app.py) -- the real Hermes agents only exist
    # as host processes, so chat messages are proxied there over HTTP.
    CHAT_BRIDGE_URL: str = "http://host.docker.internal:8910"
    CHAT_BRIDGE_TOKEN: str = ""

    # ForgeRouter dashboard SSO (see api/routes/forgerouter.py). URL is the
    # backend-to-backend address; the browser reaches ForgeRouter directly
    # via VITE_FORGEROUTER_URL on the frontend side.
    FORGEROUTER_URL: str = "http://host.docker.internal:2100"
    FORGEROUTER_SSO_SECRET: str = ""

    # Kanboard JSON-RPC integration (see app/core/kanboard_client.py). URL
    # must be reachable from inside this container -- the `kanboard`
    # hostname on the shared foundation_network, not
    # localhost (that only works from the host/browser, e.g. the iframe in
    # frontend/src/pages/kanboard/index.tsx).
    KANBOARD_URL: str = "http://kanboard/jsonrpc.php"
    KANBOARD_USER: str = ""
    KANBOARD_TOKEN: str = ""
    KANBOARD_PROJECT_ID: int = 0
    # Browser-facing base URL for card links returned to the frontend --
    # KANBOARD_URL above is the container-internal address and is not
    # resolvable from a user's browser.
    KANBOARD_PUBLIC_URL: str = "http://localhost:8081"

    # Second PostgreSQL instance (Foundation runtime data).
    # Inside Docker both instances share the foundation_network docker network.
    FOUNDATION_POSTGRES_HOST: str = "foundation_postgres"
    FOUNDATION_POSTGRES_PORT: int = 5432
    FOUNDATION_POSTGRES_USER: str = "foundation"
    FOUNDATION_POSTGRES_PASSWORD: str = ""  # falls back to POSTGRES_PASSWORD when empty

    @property
    def DATABASE_URL(self) -> str:
        """Async SQLAlchemy connection string (postgresql+asyncpg://...)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def db_url_for(self, host: str, port: int, db: str) -> str:
        """Build a connection URL for an arbitrary host/port/db using the shared credentials."""
        # Foundation instance may have its own password; fall back to main password.
        password = self.FOUNDATION_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD
        user = self.FOUNDATION_POSTGRES_USER or self.POSTGRES_USER
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
