from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.routes import systemstats as routes
from app.core.deps import get_current_user


@pytest.mark.asyncio
async def test_details_require_admin_and_never_accept_only_bridge_header(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test')
    assert (await client.get('/api/v1/system-stats/details')).status_code == 401
    assert (await client.get('/api/v1/system-stats/details', headers={'X-Bridge-Token': 'anything'})).status_code == 401
    async def normal_user():
        return SimpleNamespace(is_admin=False)
    app.dependency_overrides[get_current_user] = normal_user
    assert (await client.get('/api/v1/system-stats/details')).status_code == 403
    payload = {'collected_at': '2026-10-26T10:00:00Z', **{k: {'status': 'unavailable', 'collected_at': None, 'error': 'source', 'data': None} for k in routes.MONITORING_SOURCES}}
    async def read():
        return payload
    monkeypatch.setattr(routes, '_read_monitoring', read)
    async def admin_user():
        return SimpleNamespace(is_admin=True)
    app.dependency_overrides[get_current_user] = admin_user
    response = await client.get('/api/v1/system-stats/details')
    await client.aclose()
    assert response.status_code == 200
    assert response.json()['processes']['data'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [httpx.Response(500, text='password=SECRET'), httpx.Response(200, text='password=SECRET'), httpx.Response(200, json={'error': 'password=SECRET'})])
async def test_upstream_failure_does_not_expose_body(monkeypatch, response):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: response)
    monkeypatch.setattr(routes.httpx, 'AsyncClient', lambda **kw: real_client(transport=transport, **kw))
    with pytest.raises(Exception) as error:
        await routes._read_monitoring()
    assert error.value.status_code == 502
    assert 'SECRET' not in error.value.detail
