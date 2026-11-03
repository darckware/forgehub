import importlib.util
import os
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import assert_test_database_target, settings


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('origin', "'{\"kind\":\"contact\"}'::jsonb"), ('completed_by', "'maia'")])
async def test_direct_origin_migration_refuses_loss_of_source_or_completing_agent(field,value):
    assert settings.ENVIRONMENT == 'test', 'Isolated test environment required'
    assert_test_database_target(settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB, settings.POSTGRES_USER)
    if os.environ.get('PERSONAL_CAPTURE_TEST_RESET') != '1':
        pytest.skip('clears synthetic personal demands (rolled back): set PERSONAL_CAPTURE_TEST_RESET=1 to run')
    spec=importlib.util.spec_from_file_location('direct_migration',Path('alembic/versions/8d71e3a2f609_direct_personal_demand_origin.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            transaction=await conn.begin()
            try:
                await conn.execute(text('DELETE FROM company.personal_demands'))
                # Static parameter pairs above only; never use production/user SQL here.
                await conn.execute(text(f"INSERT INTO company.personal_demands(id,title,created_by,{field}) VALUES (gen_random_uuid(),'Migration fixture','fixture',{value})"))
                def refuse(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        with pytest.raises(RuntimeError,match='retain the additive schema'):
                            module.downgrade()
                await conn.run_sync(refuse)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
