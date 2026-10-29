"""Run only against the throwaway PostgreSQL created for this integration test."""
import asyncio
import hashlib
import json
import os
import socket
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateColumn

from app.api.routes import demand as demand_routes, moodle_approval
from app.core.config import settings
from app.core.demand_dispatch_guard import reserve_dispatch
from app.core.security import create_access_token, hash_password
from app.core.deps import get_current_user
from app.db.base import get_db
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.demand import AgentDemand, DemandAttachment
from app.db.models.governance import AuditEvent
from app.db.models.moodle_approval import MoodleApproval, MoodleChallenge
from app.db.models.operations import AgentQuestion
from app.db.models.user import User


async def main():
    db_url = os.environ['INTEGRATION_DISPOSABLE_DB']
    if db_url != 'postgresql+asyncpg://postgres:isolated-test@127.0.0.1:32769/isolated':
        raise RuntimeError('Only the explicitly created disposable database is accepted')
    engine = create_async_engine(db_url)
    tables = [User, Agent, AgentServiceCredential, AgentDemand, DemandAttachment, MoodleApproval, MoodleChallenge, AuditEvent, AgentQuestion]
    async with engine.begin() as connection:
        assert (await connection.execute(text('SELECT current_database()'))).scalar_one() == 'isolated'
        # The target must be fresh: never remove a pre-existing schema.
        await connection.execute(text('CREATE SCHEMA company'))
        for model in tables:
            table = model.__table__
            columns = ', '.join(str(CreateColumn(c).compile(dialect=connection.dialect)) for c in table.columns)
            await connection.execute(text(f'CREATE TABLE company."{table.name}" ({columns}, PRIMARY KEY (id))'))
        for col in ('request_id', 'message_id'):
            await connection.execute(text(f'CREATE UNIQUE INDEX ON company.moodle_message_approvals ({col})'))
        await connection.execute(text('CREATE UNIQUE INDEX ON company.moodle_approval_challenges (secret_hash)'))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_id, source_id, executor_id = (uuid.uuid4() for _ in range(3))
    source_token, executor_token = ('agt_' + uuid.uuid4().hex for _ in range(2))
    async with sessions() as db:
        db.add(User(id=owner_id, username='integration-owner', hashed_password=hash_password('test-owner-password'), is_admin=True, is_active=True))
        for aid, name, token in ((source_id, 'synthetic-source', source_token), (executor_id, 'synthetic-executor', executor_token)):
            db.add(Agent(id=aid, name=name, agent_type='executor', status='active', is_active=True, profile_slug=name, runtime_type='hermes'))
            db.add(AgentServiceCredential(id=uuid.uuid4(), agent_id=aid, label='synthetic', token_hash=hashlib.sha256(token.encode()).hexdigest()))
        db.add(MoodleChallenge(owner_id=owner_id, secret_hash=hashlib.sha256(b'synthetic-challenge').hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), attempts=0))
        await db.commit()
    with tempfile.TemporaryDirectory(prefix='moodle-fh-integration-') as tmp:
        settings.MOODLE_APPROVAL_ENABLED = True
        settings.MOODLE_APPROVAL_OWNER_ID = str(owner_id)
        settings.MOODLE_APPROVAL_WORKING_PATH = tmp
        settings.MOODLE_APPROVAL_SOURCE_FILES = json.dumps({str(source_id): str(Path(tmp) / 'proposals.json')})
        moodle_approval.wake_scheduled_dispatch = lambda: None
        async def no_dependencies(*_):
            return None
        demand_routes._ensure_demand_dependencies_satisfied = no_dependencies
        app = FastAPI()
        app.include_router(moodle_approval.router)
        async def isolated_db():
            async with sessions() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        class Reservation(BaseModel):
            message_id: uuid.UUID
        @app.post('/__test/reserve')
        async def reserve(body: Reservation, user: User = Depends(get_current_user), db=Depends(get_db)):
            if user.id != owner_id:
                raise HTTPException(403)
            demand = await db.get(AgentDemand, body.message_id)
            if not demand:
                raise HTTPException(404)
            await reserve_dispatch(db, demand, executor_id, None)
            return {'reserved': True}
        @app.post('/__test/complete')
        async def complete(body: Reservation, user: User = Depends(get_current_user), db=Depends(get_db)):
            if user.id != owner_id:
                raise HTTPException(403)
            demand = await db.get(AgentDemand, body.message_id)
            link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == body.message_id))
            if not demand or not link or link.state != 'finished' or link.outcome != 'completed':
                raise HTTPException(409)
            # Simulate runner completion without starting a real agent process.
            demand.dispatch_status = 'completed'
            await db.commit()
            return {'completed': True}
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        sock.listen(64)
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='warning', lifespan='off', access_log=False))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.05)
        if not server.started:
            raise RuntimeError('Isolated server did not start')
        env = dict(os.environ, INTEGRATION_HUB_URL=f'http://127.0.0.1:{port}',
            INTEGRATION_SOURCE_TOKEN=source_token, INTEGRATION_EXECUTOR_TOKEN=executor_token,
            INTEGRATION_OWNER_JWT=create_access_token('integration-owner'), INTEGRATION_EXECUTOR_ID=str(executor_id),
            INTEGRATION_PROPOSAL_DIR=tmp)
        try:
            proc = await asyncio.create_subprocess_exec('node', '--test', 'test/integration-forgehub.test.ts',
                cwd='/root/project/moodle-telegram-approval/mcp-server', env=env)
            code = await asyncio.wait_for(proc.wait(), timeout=60)
            if code:
                raise RuntimeError(f'MCP integration test failed ({code})')
        finally:
            server.should_exit = True
            await task
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
