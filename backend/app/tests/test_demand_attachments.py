"""Tests for message attachments: storage layout, naming, multi-file upload,
per-file description, and the legacy-location fallback.

What these protect (2026-07-27 changes):
  - attachments live under their own root (/messages), not the Docs mount;
  - the on-disk name is <attachment id>_<message number>_<timestamp><ext>, so
    two uploads of the same filename can never overwrite each other;
  - the uploaded name still round-trips as `filename` and as the download name;
  - rows written before the move still resolve under /docs.

Both roots are monkeypatched to tmp_path dirs -- neither /messages nor /docs
exists on a host running pytest directly, and the real ones must never be
touched by a test.
"""
import uuid
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand, DemandAttachment


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {create_access_token('test-attachments')}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
def roots(monkeypatch, tmp_path):
    """(messages_root, docs_root) as real temp dirs."""
    from app.api.routes import demand as demand_routes

    messages = tmp_path / "messages"
    docs = tmp_path / "docs"
    messages.mkdir()
    docs.mkdir()
    monkeypatch.setattr(demand_routes, "MESSAGES_ROOT", messages)
    monkeypatch.setattr(demand_routes, "DOCS_ROOT", docs)
    return messages, docs


@pytest_asyncio.fixture
async def demand_id():
    """A message to hang attachments off. It carries a registered sender
    because a message with no agent at all defaults to incubation, and an
    incubation must have an owner (2026-08-13, invariant 1) -- `from_agent`
    alone is free text and resolves to nobody. The attachment behaviour
    under test is unaffected by which agent owns the message."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sender = Agent(
            name=f"Attachment Sender {suffix}",
            agent_type="executor",
            runtime_type="claude",
            profile_slug=f"attach-sender-{suffix}",
        )
        session.add(sender)
        await session.flush()
        demand = AgentDemand(
            from_agent=sender.profile_slug,
            from_agent_id=sender.id,
            subject=f"attachment test {suffix}",
            body="body",
        )
        session.add(demand)
        await session.commit()
        await session.refresh(demand)
        did, number, sender_id = demand.id, demand.number, sender.id

    yield did, number

    async with AsyncSessionLocal() as session:
        await session.execute(delete(DemandAttachment).where(DemandAttachment.demand_id == did))
        await session.execute(delete(AgentDemand).where(AgentDemand.id == did))
        await session.execute(delete(Agent).where(Agent.id == sender_id))
        await session.commit()


async def _upload(client: AsyncClient, did, name: str, content: bytes, description: str | None = None):
    data = {"description": description} if description is not None else None
    response = await client.post(
        f"/api/v1/demands/{did}/attachments",
        files={"file": (name, content, "application/octet-stream")},
        data=data,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_file_lands_in_messages_root_not_docs(client: AsyncClient, roots, demand_id):
    messages, docs = roots
    did, number = demand_id

    await _upload(client, did, "procedimento.md", b"# ola")

    written = list(messages.iterdir())
    assert len(written) == 1
    assert written[0].read_bytes() == b"# ola"
    assert list(docs.rglob("*")) == []


async def test_stored_name_carries_id_number_and_extension(client: AsyncClient, roots, demand_id):
    messages, _ = roots
    did, number = demand_id

    attachment = await _upload(client, did, "Relatório Final.PDF", b"%PDF-1")

    stored = next(messages.iterdir()).name
    assert stored.startswith(f"{attachment['id']}_{number}_")
    assert stored.endswith(".pdf")  # extension normalized, original case dropped
    # The uploaded name is what the user sees, not what is on disk.
    assert attachment["filename"] == "Relatório Final.PDF"


async def test_same_filename_twice_does_not_overwrite(client: AsyncClient, roots, demand_id):
    """The whole point of the naming scheme: two uploads of report.pdf used to
    leave one file on disk and two rows pointing at it."""
    messages, _ = roots
    did, _ = demand_id

    first = await _upload(client, did, "report.pdf", b"first version")
    second = await _upload(client, did, "report.pdf", b"second version")

    assert first["id"] != second["id"]
    files = sorted(messages.iterdir())
    assert len(files) == 2
    assert {f.read_bytes() for f in files} == {b"first version", b"second version"}

    for attachment, expected in ((first, b"first version"), (second, b"second version")):
        response = await client.get(
            f"/api/v1/demands/{did}/attachments/{attachment['id']}/download"
        )
        assert response.status_code == 200
        assert response.content == expected


async def test_several_files_on_one_message(client: AsyncClient, roots, demand_id):
    messages, _ = roots
    did, _ = demand_id

    for name in ("a.txt", "b.csv", "c.png"):
        await _upload(client, did, name, name.encode())

    response = await client.get(f"/api/v1/demands/{did}")
    assert response.status_code == 200
    attachments = response.json()["attachments"]
    assert sorted(a["filename"] for a in attachments) == ["a.txt", "b.csv", "c.png"]
    assert len(list(messages.iterdir())) == 3


async def test_description_is_stored_and_returned(client: AsyncClient, roots, demand_id):
    did, _ = demand_id

    attachment = await _upload(
        client, did, "planilha.xlsx", b"xl", description="Custos do trimestre"
    )
    assert attachment["description"] == "Custos do trimestre"

    response = await client.get(f"/api/v1/demands/{did}")
    assert response.json()["attachments"][0]["description"] == "Custos do trimestre"


async def test_blank_description_is_stored_as_null(client: AsyncClient, roots, demand_id):
    """"No description" and "description set to blank" must not be two states."""
    did, _ = demand_id

    attachment = await _upload(client, did, "sem.txt", b"x", description="   ")
    assert attachment["description"] is None

    attachment = await _upload(client, did, "outro.txt", b"x")
    assert attachment["description"] is None


async def test_download_serves_the_uploaded_name(client: AsyncClient, roots, demand_id):
    did, _ = demand_id
    attachment = await _upload(client, did, "meu arquivo.txt", b"conteudo")

    response = await client.get(f"/api/v1/demands/{did}/attachments/{attachment['id']}/download")
    assert response.status_code == 200
    # Starlette percent-encodes per RFC 5987 when the name isn't plain ASCII
    # token text (here: the space), so match the encoded form.
    disposition = response.headers["content-disposition"]
    assert "meu%20arquivo.txt" in disposition or "meu arquivo.txt" in disposition
    # Never the on-disk name.
    assert attachment["id"] not in disposition


async def test_legacy_attachment_still_downloads_from_docs(client: AsyncClient, roots, demand_id):
    """Rows written before the move keep a /docs-relative path; reads fall back
    there instead of those attachments 404ing."""
    _, docs = roots
    did, _ = demand_id

    legacy_rel = f"anexos/demandas/{did}/antigo.txt"
    legacy_file = docs / legacy_rel
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_bytes(b"conteudo antigo")

    async with AsyncSessionLocal() as session:
        row = DemandAttachment(
            demand_id=did,
            filename="antigo.txt",
            path=legacy_rel,
            size_bytes=len(b"conteudo antigo"),
            content_type="text/plain",
        )
        session.add(row)
        await session.commit()
        attachment_id = row.id

    response = await client.get(f"/api/v1/demands/{did}/attachments/{attachment_id}/download")
    assert response.status_code == 200
    assert response.content == b"conteudo antigo"

    # And deleting it removes the legacy file, not a phantom under /messages.
    response = await client.delete(f"/api/v1/demands/{did}/attachments/{attachment_id}")
    assert response.status_code == 204
    assert not legacy_file.exists()


async def test_delete_removes_file_and_row(client: AsyncClient, roots, demand_id):
    messages, _ = roots
    did, _ = demand_id
    attachment = await _upload(client, did, "temp.bin", b"bytes")

    response = await client.delete(f"/api/v1/demands/{did}/attachments/{attachment['id']}")
    assert response.status_code == 204
    assert list(messages.iterdir()) == []

    async with AsyncSessionLocal() as session:
        remaining = (
            await session.execute(
                select(DemandAttachment).where(DemandAttachment.demand_id == did)
            )
        ).scalars().all()
    assert remaining == []


async def test_deleting_the_message_removes_its_files(client: AsyncClient, roots, demand_id):
    """Attachment rows cascade with the message, but the bytes don't -- every
    deleted message used to leak its files into the storage root."""
    messages, _ = roots
    did, _ = demand_id
    await _upload(client, did, "um.txt", b"1")
    await _upload(client, did, "dois.txt", b"2")
    assert len(list(messages.iterdir())) == 2

    response = await client.delete(f"/api/v1/demands/{did}")
    assert response.status_code == 204
    assert list(messages.iterdir()) == []


async def test_path_traversal_filename_cannot_escape_the_root(client: AsyncClient, roots, demand_id):
    """FastAPI/Starlette hands us whatever name the client sent; only the
    basename may ever reach the filesystem."""
    messages, _ = roots
    did, _ = demand_id

    await _upload(client, did, "../../etc/passwd", b"nope")

    written = list(messages.iterdir())
    assert len(written) == 1
    assert Path(written[0]).parent == messages
    assert "etc" not in str(written[0])
