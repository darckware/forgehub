import json
import uuid
import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select,delete
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker

from app.api.routes import personal,personal_contacts
from app.core.config import settings
from app.core.deps import ActorPrincipal,get_actor_principal
from app.db.base import get_db
from app.db.models.personal import PersonalCaptureSuggestion,PersonalContact,PersonalContactMessage,PersonalDemand,PersonalWhatsAppGroup
from app.db.models.governance import AuditEvent
from app.mcp.personal_group_sources import message_reference

CHAT='120363000000000123@g.us'
BASE='/api/v1/personal'

@pytest_asyncio.fixture
async def context(tmp_path,monkeypatch):
    assert settings.POSTGRES_PORT==55439 and settings.POSTGRES_DB=='forgehub_personal_capture_test', 'Fixture DB required; never run on production'
    engine=create_async_engine(settings.DATABASE_URL);sessions=async_sessionmaker(engine,expire_on_commit=False)
    record={'ts':1000.0,'quando':'2026-10-27T10:00:00Z','chat':CHAT,'grupo':'Grupo sintético','autor':'Solicitante fictício','autor_id':'fixture-author','texto':'Pedido fictício'}
    (tmp_path/'_monitoramento.json').write_text(json.dumps({'enabled':[CHAT]}))
    (tmp_path/'_grupos.json').write_text(json.dumps({CHAT:{'nome':'Grupo sintético','ultimo_ts':1000}}))
    (tmp_path/'120363000000000123.jsonl').write_text(json.dumps(record)+'\n')
    from app.core import personal_captures
    monkeypatch.setattr(personal_captures,'GROUPS_ROOT',tmp_path)
    from app.api.routes import personal_groups
    app=FastAPI();app.include_router(personal.router);app.include_router(personal_contacts.router);app.include_router(personal_groups.router)
    principal=ActorPrincipal('user',uuid.uuid4(),'fixture-owner',True)
    async def actor():return principal
    async def database():
        async with sessions() as db:yield db
    app.dependency_overrides[get_actor_principal]=actor;app.dependency_overrides[get_db]=database
    async with sessions() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_type.in_(['personal_whatsapp_group','personal_capture_suggestion'])))
        await db.execute(delete(PersonalDemand))
        await db.execute(delete(PersonalCaptureSuggestion))
        await db.execute(delete(PersonalWhatsAppGroup))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://fixture') as client:
        yield client,sessions,tmp_path,record,app
    await engine.dispose()

@pytest.mark.asyncio
async def test_group_capture_requires_real_monitored_source_and_creates_pending_uuid(context):
    client,sessions,root,record,_=context
    register=await client.post(BASE+'/groups',json={'whatsapp_id':CHAT})
    assert register.status_code==201,register.text
    group=register.json();uuid.UUID(group['id'])
    again=await client.post(BASE+'/groups',json={'whatsapp_id':CHAT});assert again.json()['id']==group['id']
    body={'whatsapp_id':CHAT,'message_ref':message_reference(CHAT,record),'title':'Demanda fictícia','details':'Detalhes fictícios'}
    response=await client.post(BASE+'/groups/captures',json=body)
    assert response.status_code==201,response.text
    captured=response.json();uuid.UUID(captured['id'])
    assert captured['status']=='pending' and captured['group_id']==group['id'] and captured['contact_id'] is None
    assert captured['source_author']=='Solicitante fictício'
    assert (await client.post(BASE+'/groups/captures',json=body)).json()['id']==captured['id']
    assert (await client.get(BASE+'/demands')).json()==[]
    visible=(await client.get(BASE+'/suggestions')).json();assert visible[0]['id']==captured['id']
    assert visible[0]['group_name']=='Grupo sintético'
    fake=await client.post(BASE+'/groups/captures',json={**body,'message_ref':'0'*64})
    assert fake.status_code in (404,422)
    (root/'_monitoramento.json').write_text('{"enabled":[]}')
    assert (await client.post(BASE+'/groups',json={'whatsapp_id':CHAT})).status_code==422
    assert (await client.get(BASE+'/groups')).json()==[]

@pytest.mark.asyncio
async def test_accept_retry_concurrency_creates_one_demand_with_structured_origin_and_audit(context):
    client,sessions,_,record,_=context
    body={'whatsapp_id':CHAT,'message_ref':message_reference(CHAT,record),'title':'Demanda fictícia','details':'Detalhes fictícios'}
    captured=(await client.post(BASE+'/groups/captures',json=body)).json()
    suggestion_id=captured['id']
    conflicting=await client.post(BASE+'/groups/captures',json={**body,'title':'Outro título'})
    assert conflicting.status_code==409
    responses=await asyncio.gather(*[client.post(BASE+f'/suggestions/{suggestion_id}:accept',json={}) for _ in range(3)])
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    ids={r.json()['created_item_id'] for r in responses};assert len(ids)==1
    demands=(await client.get(BASE+'/demands')).json();assert len(demands)==1
    assert demands[0]['origin']['group_name']=='Grupo sintético'
    assert demands[0]['origin']['author']=='Solicitante fictício'
    assert demands[0]['origin']['message_ref']==body['message_ref']
    async with sessions() as db:
        audits=list((await db.execute(select(AuditEvent).where(AuditEvent.entity_id==uuid.UUID(suggestion_id)))).scalars())
        assert [e.event_type for e in audits].count('accepted')==1
        assert all('Pedido fictício' not in json.dumps(e.payload) for e in audits)

@pytest.mark.asyncio
async def test_capture_retry_after_edited_accept_returns_original_uuid(context):
    client, _, _, record, _ = context
    body = {'whatsapp_id': CHAT, 'message_ref': message_reference(CHAT, record), 'title': 'Original'}
    captured = (await client.post(BASE+'/groups/captures', json=body)).json()
    accepted = await client.post(BASE+f"/suggestions/{captured['id']}:accept", json={'title': 'Corrigido'})
    assert accepted.status_code == 200
    retried = await client.post(BASE+'/groups/captures', json=body)
    assert retried.status_code == 201, retried.text
    assert retried.json()['id'] == captured['id']
    assert len((await client.get(BASE+'/demands')).json()) == 1

@pytest.mark.asyncio
async def test_accept_retry_normalizes_whitespace(context):
    client, _, _, record, _ = context
    captured = (await client.post(BASE+'/groups/captures', json={
        'whatsapp_id': CHAT, 'message_ref': message_reference(CHAT, record), 'title': 'Original'
    })).json()
    payload = {'title': ' Corrigido ', 'details': ' Detalhes '}
    first = await client.post(BASE+f"/suggestions/{captured['id']}:accept", json=payload)
    retried = await client.post(BASE+f"/suggestions/{captured['id']}:accept", json=payload)
    assert first.status_code == retried.status_code == 200, retried.text
    assert first.json()['created_item_id'] == retried.json()['created_item_id']

@pytest.mark.asyncio
async def test_dismiss_waits_for_accept_decision_and_audits_discard(context):
    from app.api.routes.personal_contacts import dismiss_suggestion
    from fastapi import HTTPException
    client, sessions, _, record, _ = context
    body = {'whatsapp_id': CHAT, 'message_ref': message_reference(CHAT, record), 'title': 'Original'}
    captured = (await client.post(BASE+'/groups/captures', json=body)).json()
    sid = uuid.UUID(captured['id'])
    async with sessions() as owner, sessions() as contender:
        suggestion = (await owner.execute(select(PersonalCaptureSuggestion).where(PersonalCaptureSuggestion.id == sid).with_for_update())).scalar_one()
        pending = asyncio.create_task(dismiss_suggestion(sid, 'fixture-owner', contender))
        await asyncio.sleep(0.1)
        waited = not pending.done()
        suggestion.status = 'accepted'
        await owner.commit()
        try:
            await pending
            rejected = False
        except HTTPException as exc:
            rejected = exc.status_code == 409
        await contender.rollback()
    assert waited, 'Discard must wait for the competing acceptance transaction'
    assert rejected, 'Discard must preserve a committed acceptance'
    captured = (await client.post(BASE+'/groups/captures', json={**body, 'item_key': 'discard'})).json()
    response = await client.post(BASE+f"/suggestions/{captured['id']}:dismiss")
    assert response.status_code == 200, response.text
    async with sessions() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(captured['id']), AuditEvent.event_type == 'dismissed'))).scalars().all()
        assert len(events) == 1 and events[0].actor == 'marcelo'

@pytest.mark.asyncio
async def test_personal_groups_remain_private(context):
    client,_,_,_,app=context
    app.dependency_overrides.pop(get_actor_principal)
    assert (await client.get(BASE+'/groups')).status_code==401
    async def nonadmin():return ActorPrincipal('user',uuid.uuid4(),'fixture-normal',False)
    app.dependency_overrides[get_actor_principal]=nonadmin
    assert (await client.post(BASE+'/groups',json={'whatsapp_id':CHAT})).status_code==403

@pytest.mark.asyncio
async def test_contact_capture_still_records_original_contact_and_message(context):
    from datetime import datetime, timezone
    client,sessions,_,_,_=context
    async with sessions() as db:
        contact=PersonalContact(phone='5599'+str(uuid.uuid4().int%1000000000).zfill(9),name='Contato fictício')
        db.add(contact);await db.flush()
        message=PersonalContactMessage(contact_id=contact.id,at=datetime(2026,10,20,9,tzinfo=timezone.utc),direction='in',author='Origem fictícia',text='Pedido fictício',source='whatsapp')
        db.add(message);await db.flush()
        suggestion=PersonalCaptureSuggestion(contact_id=contact.id,message_id=message.id,kind='demand',title='Pedido de contato',details='',status='pending')
        db.add(suggestion);await db.commit();sid=suggestion.id;mid=message.id
    response=await client.post(BASE+f'/suggestions/{sid}:accept',json={})
    assert response.status_code==200,response.text
    demand=(await client.get(BASE+'/demands')).json()[0]
    assert demand['origin']['kind']=='contact' and demand['origin']['contact_name']=='Contato fictício'
    assert demand['origin']['message_id']==str(mid)
    assert demand['origin']['author']=='Origem fictícia'
    assert demand['origin']['captured_at'].startswith('2026-10-20T09:00')

@pytest.mark.asyncio
async def test_scoped_maia_can_capture_but_another_agent_cannot(context, monkeypatch):
    from app.db.models.agent import Agent
    client, sessions, _, record, app = context
    monkeypatch.setattr(settings, 'PERSONAL_AGENT_SLUGS', 'maia')
    async with sessions() as db:
        maia = Agent(name='Fixture Maia '+str(uuid.uuid4()), profile_slug='maia')
        other = Agent(name='Fixture Other '+str(uuid.uuid4()), profile_slug='fixture-other')
        db.add_all([maia, other]); await db.commit()
        maia_id, other_id = maia.id, other.id
    async def agent(): return ActorPrincipal('agent', maia_id, 'fixture-maia', False)
    app.dependency_overrides[get_actor_principal] = agent
    body = {'whatsapp_id': CHAT, 'message_ref': message_reference(CHAT,record), 'title':'Demanda fictícia'}
    try:
        responses = await asyncio.gather(*[client.post(BASE+'/groups/captures',json=body) for _ in range(3)])
        assert all(r.status_code==201 for r in responses), [r.text for r in responses]
        assert len({r.json()['id'] for r in responses})==1
        async def denied(): return ActorPrincipal('agent', other_id, 'fixture-other', False)
        app.dependency_overrides[get_actor_principal] = denied
        assert (await client.post(BASE+'/groups/captures',json=body)).status_code==403
    finally:
        async with sessions() as db:
            await db.execute(delete(Agent).where(Agent.id.in_([maia_id, other_id]))); await db.commit()
