import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('origin', "'{\"kind\":\"contact\"}'::jsonb"), ('completed_by', "'maia'")])
async def test_direct_origin_migration_refuses_loss_of_source_or_completing_agent(field,value):
    assert settings.POSTGRES_PORT==55439 and settings.POSTGRES_DB=='forgehub_personal_capture_test'
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
