"""Tests for the Foundation page's Scripts registry: manual CRUD plus the
doc-driven /sync scan. DB strategy matches test_demand.py -- real DB,
UUID-suffixed rows cleaned up in a finally block. /sync's filesystem reads
(FOUNDATION_ROOT, PROFILES_DIR) are monkeypatched to tmp_path since neither
mount exists on the host running pytest directly.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.foundation_script import FoundationScript


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-foundation-script')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


async def _cleanup(*names: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(FoundationScript).where(FoundationScript.name.in_(names)))
        await session.commit()


async def test_create_list_update_delete(client: AsyncClient):
    name = f"telegram_audio_{uuid.uuid4().hex[:8]}.py"
    try:
        resp = await client.post(
            "/api/v1/foundation-scripts",
            json={"name": name, "description": "Transcribes Telegram voice notes"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["source"] == "manual"
        assert body["description"] == "Transcribes Telegram voice notes"
        script_id = body["id"]

        resp = await client.get("/api/v1/foundation-scripts")
        assert resp.status_code == 200
        assert any(s["name"] == name for s in resp.json())

        resp = await client.patch(f"/api/v1/foundation-scripts/{script_id}", json={"path": "/tmp/x.py"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["path"] == "/tmp/x.py"
        assert resp.json()["source"] == "manual"

        resp = await client.delete(f"/api/v1/foundation-scripts/{script_id}")
        assert resp.status_code == 204

        resp = await client.get("/api/v1/foundation-scripts")
        assert not any(s["name"] == name for s in resp.json())
    finally:
        await _cleanup(name)


async def test_create_duplicate_name_conflicts(client: AsyncClient):
    name = f"dup_{uuid.uuid4().hex[:8]}.sh"
    try:
        resp = await client.post("/api/v1/foundation-scripts", json={"name": name})
        assert resp.status_code == 201
        resp = await client.post("/api/v1/foundation-scripts", json={"name": name})
        assert resp.status_code == 409
    finally:
        await _cleanup(name)


async def test_sync_discovers_scripts_mentioned_in_docs(client: AsyncClient, monkeypatch, tmp_path):
    from app.api.routes import foundation_script as fs

    foundation_root = tmp_path / "foundation-root"
    (foundation_root / "integrations").mkdir(parents=True)
    doc = foundation_root / "integrations" / "telegram.md"
    doc.write_text(
        "Voice notes are transcribed by `telegram_audio_transcriber.py` "
        "before being handed to the agent. See also `helper.py` for a "
        "generic example.\n"
    )

    profiles_dir = tmp_path / "profiles"
    script_path = profiles_dir / "athos" / "scripts"
    script_path.mkdir(parents=True)
    (script_path / "telegram_audio_transcriber.py").write_text("# real script\n")

    monkeypatch.setattr(fs, "FOUNDATION_ROOT", foundation_root)
    monkeypatch.setattr(fs, "PROFILES_DIR", profiles_dir)

    name = "telegram_audio_transcriber.py"
    try:
        resp = await client.post("/api/v1/foundation-scripts/sync")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["added"] == 1
        assert body["scanned_docs"] == 1
        assert name in body["discovered"]
        # helper.py is mentioned but doesn't exist as a real script anywhere
        # -- generic example filenames in skill docs must not be registered.
        assert "helper.py" not in body["discovered"]

        resp = await client.get("/api/v1/foundation-scripts")
        row = next(s for s in resp.json() if s["name"] == name)
        assert row["source"] == "sync"
        assert row["doc_path"] == "integrations/telegram.md"
        assert row["path"] == str(script_path / name)
        # Description is auto-filled from the sentence the script was
        # mentioned in, not left empty for the operator to fill in by hand.
        assert row["description"] is not None
        assert "transcribed" in row["description"]

        # Re-running sync must not duplicate the already-registered row.
        resp = await client.post("/api/v1/foundation-scripts/sync")
        assert resp.status_code == 200
        assert resp.json()["added"] == 0
        assert resp.json()["already_registered"] == 1
    finally:
        await _cleanup(name)


async def test_sync_404s_when_foundation_root_not_mounted(client: AsyncClient, monkeypatch, tmp_path):
    from app.api.routes import foundation_script as fs

    monkeypatch.setattr(fs, "FOUNDATION_ROOT", tmp_path / "does-not-exist")
    resp = await client.post("/api/v1/foundation-scripts/sync")
    assert resp.status_code == 404


async def test_content_reads_registered_path(client: AsyncClient, tmp_path):
    name = f"content_{uuid.uuid4().hex[:8]}.sh"
    script_file = tmp_path / name
    script_file.write_text("echo hello\n")
    try:
        resp = await client.post("/api/v1/foundation-scripts", json={"name": name, "path": str(script_file)})
        assert resp.status_code == 201
        script_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/foundation-scripts/{script_id}/content")
        assert resp.status_code == 200, resp.text
        assert resp.json()["content"] == "echo hello\n"
    finally:
        await _cleanup(name)


async def test_content_404s_without_a_registered_path(client: AsyncClient):
    name = f"nopath_{uuid.uuid4().hex[:8]}.sh"
    try:
        resp = await client.post("/api/v1/foundation-scripts", json={"name": name})
        assert resp.status_code == 201
        script_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/foundation-scripts/{script_id}/content")
        assert resp.status_code == 404
    finally:
        await _cleanup(name)
