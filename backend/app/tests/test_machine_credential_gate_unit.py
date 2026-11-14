"""Credential identity regressions with in-memory boundaries; no database IO."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes import server as routes
from app.api.schemas.vpn import VpnNode, VpnStatus
from app.core.remote_authority import require_managed_machines
from app.db.models.server import Server

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMQ97vnwnBBhgd4AiT2WLx7Z5qEVdq6sB3KPgSX3fd7C"


@pytest.mark.asyncio
async def test_verified_machine_with_pending_preparation_is_refused_before_agent_ssh():
    server = SimpleNamespace(id=uuid.uuid4(), name="pending", remote_user="darckware",
        ssh_key_ref="candidate-key", login_password_ref="password", public_key=KEY,
        access_verified_at=datetime.now(timezone.utc), preparation_pending=True)
    with patch("app.core.ssh_key_uniqueness.find_key_owner", AsyncMock(return_value=None)) as owner:
        with pytest.raises(HTTPException) as caught:
            await require_managed_machines(AsyncMock(), [server])
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "MACHINE_RECONFIGURATION_REQUIRED"
    owner.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("match_by", ["name", "ip"])
async def test_first_tailnet_association_clears_previous_ssh_identity_proof(match_by):
    verified = datetime.now(timezone.utc)
    server = Server(id=uuid.uuid4(), name="station" if match_by == "name" else "other-name",
                    ip_address="100.64.0.1", remote_user="darckware", kind="workstation",
                    access_verified_at=verified)
    peer_ip = "100.64.0.2" if match_by == "name" else server.ip_address
    await _sync(server, node_id="new-node", peer_ip=peer_ip)
    assert server.tailnet_node_id == "new-node"
    assert server.ip_address == peer_ip
    assert server.access_verified_at is None


@pytest.mark.asyncio
async def test_same_tailnet_node_keeps_identity_proof_when_address_rotates():
    verified = datetime.now(timezone.utc)
    server = Server(id=uuid.uuid4(), name="station", ip_address="100.64.0.1",
                    remote_user="darckware", kind="workstation", tailnet_node_id="confirmed-node",
                    access_verified_at=verified)
    await _sync(server, node_id="confirmed-node", peer_ip="100.64.0.2")
    assert server.ip_address == "100.64.0.2"
    assert server.access_verified_at == verified


async def _sync(server, *, node_id, peer_ip):
    result = MagicMock()
    result.scalars.return_value.all.return_value = [server]
    db = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())
    status = VpnStatus(backend_state="Running", server=VpnNode(id="self", state="online"),
                       peers=[VpnNode(id=node_id, name="station", hostname="station", os="linux", state="online",
                                      tailscale_ipv4=peer_ip, online=True)],
                       checked_at=datetime.now(timezone.utc))
    with patch.object(routes, "fetch_tailnet_status", AsyncMock(return_value=status)):
        await routes.sync_from_tailnet(db=db, _admin=SimpleNamespace(username="admin"))
    db.commit.assert_awaited_once()
