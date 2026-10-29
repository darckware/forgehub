"""Exercise the new migration only on the explicitly isolated fixture database."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


@pytest.mark.asyncio
async def test_migration_refuses_destructive_rollback_and_preserves_contacts():
    assert settings.POSTGRES_PORT == 55439 and settings.POSTGRES_DB == 'forgehub_personal_capture_test'
    spec = importlib.util.spec_from_file_location('capture_migration', Path('alembic/versions/6b20f44a9e12_personal_whatsapp_group_capture.py'))
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO company.personal_whatsapp_groups(id, whatsapp_id, name, created_by) VALUES (gen_random_uuid(), '999999999999@g.us', 'Migration fixture', 'fixture') ON CONFLICT DO NOTHING"))
            def refuse(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    with pytest.raises(RuntimeError, match='keep the additive schema'):
                        migration.downgrade()
            await conn.run_sync(refuse)
            before = (await conn.execute(text('SELECT count(*) FROM company.personal_contacts'))).scalar_one()
            # Synthetic fixture records only; required to exercise the reversible empty state.
            await conn.execute(text('DELETE FROM company.personal_capture_suggestions WHERE group_id IS NOT NULL'))
            await conn.execute(text('DELETE FROM company.personal_whatsapp_groups'))
            def cycle(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.downgrade()
                    migration.upgrade()
            await conn.run_sync(cycle)
            after = (await conn.execute(text('SELECT count(*) FROM company.personal_contacts'))).scalar_one()
            assert after == before
    finally:
        await engine.dispose()
