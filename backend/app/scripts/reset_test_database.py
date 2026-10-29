"""Reset the isolated test database to an empty schema at Alembic head.

    ENVIRONMENT=test python -m app.scripts.reset_test_database [--seed]

(test-env/reset.sh runs it in the test tools container.) Plano Integrado T.1;
`--seed` (T.2) then applies the fictitious seed (seed_test_database.py).

Refuses before connecting unless ENVIRONMENT=test and the target is on the
test allowlist (app/core/config.py). After connecting -- and still before
touching anything -- it checks the server itself: the session must be
forgehub_test on database forgehub_test, and the server must not host a
database named `forgehub`, which is what a production instance would have.
Only then are the `company` and `public` schemas dropped, recreated and
migrated.
"""
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _refuse(message: str) -> None:
    print(f"reset refused: {message}", file=sys.stderr)
    sys.exit(2)


def _load_settings():
    try:
        from app.core.config import (
            assert_test_database_target,
            is_test_environment,
            settings,
        )
    except Exception as exc:  # Settings itself refused the target
        _refuse(str(exc))
    if not is_test_environment(settings.ENVIRONMENT):
        _refuse(f"ENVIRONMENT must be 'test' (got {settings.ENVIRONMENT!r})")
    try:
        assert_test_database_target(
            settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB, settings.POSTGRES_USER
        )
    except Exception as exc:
        _refuse(str(exc))
    return settings


async def assert_test_server(conn) -> None:
    """Refuse unless the connected server is the test instance. Shared with
    seed_test_database.py; runs before anything is written."""
    from sqlalchemy import text

    db, user = (await conn.execute(text("SELECT current_database(), current_user"))).one()
    if db != "forgehub_test" or user != "forgehub_test":
        _refuse(f"server session is {user}@{db}, expected forgehub_test@forgehub_test")
    production_db = (
        await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'forgehub'"))
    ).first()
    if production_db is not None:
        _refuse("the server hosts a database named 'forgehub' -- this is not the test instance")


async def _wipe_schema(settings) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    schema = settings.POSTGRES_SCHEMA
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await assert_test_server(conn)
            # `public` too: an early migration creates its enum types there
            # (unqualified CREATE TYPE), and they would survive a reset of
            # `company` alone and make the next upgrade fail.
            for name in (schema, "public"):
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
                await conn.execute(text(f'CREATE SCHEMA "{name}" AUTHORIZATION forgehub_test'))
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    unknown = [a for a in args if a != "--seed"]
    if unknown:
        _refuse(f"unknown argument(s): {' '.join(unknown)} (only --seed)")
    settings = _load_settings()
    asyncio.run(_wipe_schema(settings))
    print(f"schemas {settings.POSTGRES_SCHEMA!r} and 'public' recreated on forgehub_test; migrating to head")

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(_BACKEND_DIR / "alembic.ini")), "head")
    if "--seed" not in args:
        print("reset done: forgehub_test is empty at Alembic head")
        return

    from app.scripts.seed_test_database import main as seed_main

    seed_main()


if __name__ == "__main__":
    main()
