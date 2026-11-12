"""Machine status monitor (Remote Access phase 4, gap 10): the pass is run
directly with the tailnet and the SSH probe stubbed -- no network. Each test
scopes the pass to its own rows (`server_ids`) and fixes `now` on a far-future
date of its own, so the per-day keys never collide with real rows."""
import random
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select, text

from app.api.routes import server as server_routes
from app.api.schemas.vpn import VpnNode, VpnStatus
from app.core import machine_status_monitor as monitor
from app.core.machine_status_monitor import is_mass_degrade, run_machine_status_pass, transition_kind
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.machine_status import MachineStatusObservation
from app.db.models.notification import Notification
from app.db.models.profile import Profile, ProfilePermission
from app.db.models.server import Server
from app.db.models.user import User


class Fake:
    """The two readiness sources, steerable per pass."""

    def __init__(self):
        self.tailnet_available = True
        self.self_state = "online"  # the VPS's own state when the tailnet is readable
        self.on_probe = None  # optional async hook run inside the probe (mid-pass)
        self.online: dict[str, bool] = {}  # node id -> online
        self.probe_down = False
        self.ssh: dict[str, str] = {}  # server id -> probe answer (missing = no answer)
        self.probe_calls = 0

    async def tailnet(self):
        peers = [
            VpnNode(id=n, name=n, tailscale_ipv4="100.127.9.9", os="windows",
                    state="online" if on else "offline", online=on)
            for n, on in self.online.items()
        ] if self.tailnet_available else []
        return VpnStatus(
            backend_state="Running" if self.tailnet_available else "Unavailable",
            server=VpnNode(id="self", state=self.self_state if self.tailnet_available else "unavailable"),
            peers=peers,
            checked_at=datetime.now(timezone.utc),
        )

    async def probe(self, servers):
        self.probe_calls += 1
        if self.on_probe is not None:
            await self.on_probe()
        if self.probe_down:
            return None
        return {str(s.id): self.ssh[str(s.id)] for s in servers if str(s.id) in self.ssh}


@pytest_asyncio.fixture
async def env():
    tag = f"t{uuid.uuid4().hex[:8]}"
    day = datetime(2031, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=random.randint(0, 3000))
    fake = Fake()
    created: list[uuid.UUID] = []

    async def add(name: str, *, online=True, ssh="active", **kw) -> Server:
        node = f"{tag}{name}"
        async with AsyncSessionLocal() as db:
            row = Server(
                name=f"{name}-{tag}", ip_address="100.127.9.9", remote_user="darckware",
                tailnet_node_id=node, darckware_client_name="Cliente Teste", **kw,
            )
            db.add(row)
            await db.commit()
        fake.online[node] = online
        if ssh is not None:
            fake.ssh[str(row.id)] = ssh
        created.append(row.id)
        return row

    async def run(at: datetime):
        server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
        with (
            patch.object(server_routes, "fetch_tailnet_status", AsyncMock(side_effect=fake.tailnet)),
            patch.object(server_routes, "_probe_many_via_bridge", AsyncMock(side_effect=fake.probe)),
        ):
            async with AsyncSessionLocal() as db:
                return await run_machine_status_pass(db, now=at, server_ids=set(created))

    def day_keys():
        d = day.date().isoformat()
        return [f"machine-status-summary:{d}", f"machine-status-unavailable:{d}"]

    async def cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Notification).where(or_(
                Notification.event_key.in_(day_keys()),
                Notification.event_key.like(f"machine-status-mass%:{day.date().isoformat()}T%"),
                *[Notification.event_key.like(f"machine-status:{sid}:%") for sid in created],
            )))
            await db.execute(delete(Server).where(Server.name.like(f"%{tag}%")))
            await db.commit()

    await cleanup()
    yield type("Env", (), {"fake": fake, "add": staticmethod(add), "run": staticmethod(run), "day": day,
                          "tag": tag, "created": created})
    await cleanup()


async def _notification(key: str) -> Notification | None:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Notification).where(Notification.event_key == key))).scalar_one_or_none()


async def _observation(server_id) -> MachineStatusObservation | None:
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(MachineStatusObservation).where(MachineStatusObservation.server_id == server_id)
        )).scalar_one_or_none()


@pytest.mark.parametrize(
    "previous, current, expected",
    [
        ("complete", "partial", "degraded"),
        ("complete", "offline", "degraded"),
        ("partial", "offline", "degraded"),
        ("partial", "not_prepared", "degraded"),
        ("offline", "unknown", "degraded"),
        ("offline", "partial", None),
        ("not_prepared", "partial", None),
        ("offline", "complete", "recovered"),
        ("complete", "complete", None),
    ],
)
def test_transition_kind(previous, current, expected):
    assert transition_kind(previous, current) == expected


@pytest.mark.asyncio
async def test_first_pass_is_a_silent_baseline_with_one_summary(env):
    ok = await env.add("ok")
    off = await env.add("off", online=False)
    bare = await env.add("bare", ssh="not_installed")

    first = await env.run(env.day)
    summary_key = f"machine-status-summary:{env.day.date().isoformat()}"
    assert first.baselined == 3 and first.changed == 0
    assert first.alerts == [summary_key]
    summary = await _notification(summary_key)
    assert summary.severity == "warning" and summary.title.startswith("2 máquinas")
    assert f"off-{env.tag} (Cliente Teste)" in summary.message and f"bare-{env.tag}" in summary.message
    assert f"ok-{env.tag}" not in summary.message
    assert (await _observation(ok.id)).status == "complete"
    assert (await _observation(off.id)).status == "offline"
    assert (await _observation(bare.id)).status == "not_prepared"

    # A later pass (or a restart: nothing is in memory) alerts nothing more.
    again = await env.run(env.day + timedelta(minutes=15))
    assert again.alerts == [] and again.baselined == 0 and again.changed == 0
    assert (await _observation(off.id)).since == env.day


@pytest.mark.asyncio
async def test_transitions_alert_once_recover_and_alert_again(env):
    machine = await env.add("ws")
    node = f"{env.tag}ws"
    t = [env.day + timedelta(minutes=15 * i) for i in range(8)]

    assert (await env.run(t[0])).alerts == []  # baseline complete: no summary

    env.fake.online[node] = False
    first_seen = await env.run(t[1])  # debounce: seen once, nothing yet
    assert first_seen.alerts == [] and first_seen.pending == 1
    obs = await _observation(machine.id)
    assert obs.status == "complete" and obs.pending_status == "offline" and obs.pending_since == t[1]

    down = await env.run(t[2])  # confirmed: alerts with the instant first seen
    key_down = f"machine-status:{machine.id}:offline:{t[1].isoformat()}"
    assert down.alerts == [key_down]
    alert = await _notification(key_down)
    assert alert.severity == "warning" and alert.source == "system"
    assert f"ws-{env.tag} (Cliente Teste)" in alert.title
    assert "de completo para offline" in alert.message and "/remote-access" in alert.message
    assert "Motivo: offline na tailnet." in alert.message

    # Still offline: no duplicate, and "since" keeps the transition instant.
    assert (await env.run(t[3])).alerts == []
    obs = await _observation(machine.id)
    assert obs.status == "offline" and obs.since == t[1] and obs.last_checked_at == t[3]
    assert obs.pending_status is None

    env.fake.online[node] = True
    back = await env.run(t[4])  # a recovery alerts on the first pass
    key_back = f"machine-status:{machine.id}:complete:{t[4].isoformat()}"
    assert back.alerts == [key_back]
    recovered = await _notification(key_back)
    assert recovered.severity == "info" and recovered.title.startswith("Máquina voltou")

    env.fake.online[node] = False
    assert (await env.run(t[5])).alerts == []
    again = await env.run(t[6])
    assert again.alerts == [f"machine-status:{machine.id}:offline:{t[5].isoformat()}"]


@pytest.mark.asyncio
async def test_a_one_pass_blip_never_alerts(env):
    """The debounce: a degrade seen on one pass only (a probe hiccup) is
    forgotten when the next pass sees the machine complete again."""
    machine = await env.add("blip")
    await env.run(env.day)
    env.fake.ssh[str(machine.id)] = "not_installed"
    assert (await env.run(env.day + timedelta(minutes=15))).alerts == []
    env.fake.ssh[str(machine.id)] = "active"
    result = await env.run(env.day + timedelta(minutes=30))
    assert result.alerts == [] and result.changed == 0
    obs = await _observation(machine.id)
    assert obs.status == "complete" and obs.since == env.day and obs.pending_status is None


@pytest.mark.asyncio
async def test_per_machine_unknown_from_a_readable_source_is_a_transition(env):
    machine = await env.add("unk")
    await env.run(env.day)
    del env.fake.ssh[str(machine.id)]  # the bridge answered, but not for this machine
    t1, t2 = env.day + timedelta(minutes=15), env.day + timedelta(minutes=30)
    assert (await env.run(t1)).alerts == []
    result = await env.run(t2)
    assert not result.source_unavailable
    assert result.alerts == [f"machine-status:{machine.id}:unknown:{t1.isoformat()}"]
    assert "Motivo: não foi possível sondar o SSH." in (await _notification(result.alerts[0])).message


@pytest.mark.parametrize("degraded, scope, expected", [
    (1, 1, False), (1, 2, False), (2, 3, True), (2, 4, False), (4, 20, False), (5, 20, True),
])
def test_is_mass_degrade(degraded, scope, expected):
    assert is_mass_degrade(degraded, scope) is expected


@pytest.mark.asyncio
async def test_bridge_answering_not_installed_for_every_machine_is_one_mass_summary(env):
    """A ForgeVault/ssh-agent hiccup: the bridge answers `not_installed` for
    every vault-key machine. One summary, not one alert each -- and their
    recoveries are grouped the same way."""
    rows = [await env.add(f"m{i}") for i in range(3)]
    keep = await env.add("still", online=False)  # already offline: not part of the batch
    await env.run(env.day)
    for row in rows:
        env.fake.ssh[str(row.id)] = "not_installed"
    t1, t2, t3 = (env.day + timedelta(minutes=15 * i) for i in (1, 2, 3))
    assert (await env.run(t1)).alerts == []
    mass = await env.run(t2)
    assert mass.mass_degrade and mass.alerts == [f"machine-status-mass:{t2.isoformat()}"]
    summary = await _notification(mass.alerts[0])
    assert summary.title == "3 máquinas mudaram de estado ao mesmo tempo"
    assert "possível falha da sondagem, do ForgeVault ou da rede da VPS" in summary.message
    for row in rows:
        obs = await _observation(row.id)
        assert obs.status == "not_prepared" and obs.mass_batch and obs.since == t1
    assert (await _observation(keep.id)).status == "offline"

    for row in rows:
        env.fake.ssh[str(row.id)] = "active"
    back = await env.run(t3)
    assert back.alerts == [f"machine-status-mass-recovered:{t3.isoformat()}"]
    grouped = await _notification(back.alerts[0])
    assert grouped.severity == "info" and grouped.title == "3 máquinas voltaram ao estado completo"
    for row in rows:
        obs = await _observation(row.id)
        assert obs.status == "complete" and not obs.mass_batch


@pytest.mark.asyncio
@pytest.mark.parametrize("vps_state", ["needs_login", "offline"])
async def test_vps_not_online_in_the_tailnet_records_nothing(env, vps_state):
    machine = await env.add("vps")
    await env.run(env.day)
    env.fake.self_state = vps_state
    env.fake.online[f"{env.tag}vps"] = False  # what an unreadable tailnet might claim
    for i in (1, 2):
        result = await env.run(env.day + timedelta(minutes=15 * i))
        assert result.source_unavailable
    assert (await _notification(f"machine-status-unavailable:{env.day.date().isoformat()}")) is not None
    obs = await _observation(machine.id)
    assert obs.status == "complete" and obs.pending_status is None and obs.last_checked_at == env.day


@pytest.mark.asyncio
async def test_lock_held_elsewhere_skips_the_pass(env):
    machine = await env.add("lock")
    async with AsyncSessionLocal() as other:
        await other.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": monitor._PASS_LOCK_KEY})
        result = await env.run(env.day)
        await other.rollback()
    assert result.skipped and result.alerts == []
    assert await _observation(machine.id) is None


@pytest.mark.asyncio
async def test_machine_deleted_mid_pass_is_skipped(env):
    """No transaction is open during the network calls, so a delete during
    the probe goes through; the pass skips that machine and keeps the rest."""
    gone = await env.add("gone")
    kept = await env.add("kept")

    async def delete_gone():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Server).where(Server.id == gone.id))
            await db.commit()

    env.fake.on_probe = delete_gone
    result = await env.run(env.day)
    assert result.baselined == 1
    assert await _observation(gone.id) is None
    assert (await _observation(kept.id)).status == "complete"


def test_every_readiness_detail_has_a_pt_br_reason():
    details = set()
    for kw in (dict(access_enabled=False), dict(remote_user=""), dict(ip_address=""), dict()):
        for online in (None, True, False):
            for ssh in (None, "active", "not_installed", "off"):
                fields = {"ip_address": "100.127.0.1", "remote_user": "u", "access_enabled": True,
                          "tailnet_node_id": "n", **kw}
                row = Server(name="x", **fields)
                readiness, detail = server_routes.classify_readiness(
                    row, tailnet_available=True, tailnet_online=online, ssh=ssh
                )
                details.add(detail)
                for kind, rustdesk in (("workstation", None), ("workstation", "1"), ("server", None)):
                    row.kind, row.rustdesk_id = kind, rustdesk
                    details.add(server_routes.classify_status(row, readiness)[1])
    details.discard(None)
    assert details <= set(server_routes.READINESS_DETAIL_PT)
    assert monitor._reason_pt("something new") is None


@pytest.mark.asyncio
async def test_probe_bridge_down_records_nothing_and_warns_once(env):
    up = await env.add("up")
    down = await env.add("down", online=False)
    await env.run(env.day)  # baseline: complete + offline

    env.fake.probe_down = True
    env.fake.online[f"{env.tag}down"] = True  # would be a "voltou" -- must not be
    t1 = env.day + timedelta(minutes=15)
    result = await env.run(t1)
    unavailable_key = f"machine-status-unavailable:{env.day.date().isoformat()}"
    assert result.source_unavailable and result.alerts == [unavailable_key]
    notice = await _notification(unavailable_key)
    assert notice.title == "Monitoramento das máquinas indisponível" and "sondagem SSH" in notice.message
    assert (await _observation(up.id)).status == "complete"
    obs_down = await _observation(down.id)
    assert obs_down.status == "offline" and obs_down.last_checked_at == env.day

    # Same day: no second notice.
    assert (await env.run(t1 + timedelta(minutes=15))).alerts == []

    env.fake.probe_down = False
    healed = await env.run(t1 + timedelta(minutes=30))
    assert healed.alerts == [f"machine-status:{down.id}:complete:{(t1 + timedelta(minutes=30)).isoformat()}"]


@pytest.mark.asyncio
async def test_tailnet_down_records_nothing(env):
    machine = await env.add("tn")
    await env.run(env.day)
    env.fake.tailnet_available = False
    result = await env.run(env.day + timedelta(minutes=15))
    assert result.source_unavailable
    assert result.alerts == [f"machine-status-unavailable:{env.day.date().isoformat()}"]
    assert "a tailnet" in (await _notification(result.alerts[0])).message
    assert (await _observation(machine.id)).status == "complete"


@pytest.mark.asyncio
async def test_disabled_machines_are_ignored_and_lose_their_baseline(env):
    disabled = await env.add("dis", online=False, access_enabled=False)
    active = await env.add("act")
    first = await env.run(env.day)
    assert first.baselined == 1 and first.alerts == []
    assert await _observation(disabled.id) is None

    # Disabling an observed machine drops its row: re-enabling starts silent.
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, active.id)
        row.access_enabled = False
        await db.commit()
    env.fake.online[f"{env.tag}act"] = False
    assert (await env.run(env.day + timedelta(minutes=15))).alerts == []
    assert await _observation(active.id) is None


@pytest.mark.asyncio
async def test_observation_goes_with_its_machine(env):
    machine = await env.add("gone")
    await env.run(env.day)
    assert await _observation(machine.id) is not None
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Server).where(Server.id == machine.id))
        await db.commit()
    assert await _observation(machine.id) is None


@pytest.mark.asyncio
async def test_compute_readiness_reuses_the_probe_cache():
    """The monitor reads through compute_readiness, which keeps the 5-minute
    SSH probe cache: two reads in a row probe at most once."""
    calls = []

    async def probe(servers):
        calls.append(len(servers))
        return {str(s.id): "off" for s in servers}

    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
    with (
        patch.object(server_routes, "fetch_tailnet_status", AsyncMock(side_effect=Fake().tailnet)),
        patch.object(server_routes, "_probe_many_via_bridge", probe),
    ):
        async with AsyncSessionLocal() as db:
            await server_routes.compute_readiness(db)
            first = len(calls)
            await server_routes.compute_readiness(db)
    assert first <= 1 and len(calls) == first


@pytest.mark.asyncio
async def test_readiness_shows_since_only_for_the_observed_status(env):
    machine = await env.add("since")
    await env.run(env.day)

    async def readiness():
        server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
        with (
            patch.object(server_routes, "fetch_tailnet_status", AsyncMock(side_effect=env.fake.tailnet)),
            patch.object(server_routes, "_probe_many_via_bridge", AsyncMock(side_effect=env.fake.probe)),
        ):
            async with AsyncSessionLocal() as db:
                result = await server_routes.get_readiness(refresh=False, db=db, _user=None)
        return next(e for e in result.entries if e.server_id == machine.id)

    entry = await readiness()
    assert entry.status == "complete" and entry.status_since == env.day
    env.fake.online[f"{env.tag}since"] = False  # the monitor hasn't seen this yet
    entry = await readiness()
    assert entry.status == "offline" and entry.status_since is None


@pytest.mark.asyncio
async def test_readiness_over_http_for_admin_and_servers_module(env, admin_headers):
    """GET /servers/readiness through HTTP with the new `status_since`: an
    admin and a non-admin with servers.view both read it; no permission, 403."""
    machine = await env.add("http")
    await env.run(env.day)
    tag = uuid.uuid4().hex[:12]
    async with AsyncSessionLocal() as db:
        profile = Profile(name=f"test-servers-{tag}")
        db.add(profile)
        await db.flush()
        db.add(ProfilePermission(profile_id=profile.id, module="servers", can_view=True))
        db.add(User(username=f"test-servers-{tag}", hashed_password=hash_password(tag), profile_id=profile.id))
        db.add(User(username=f"test-noperm-{tag}", hashed_password=hash_password(tag)))
        await db.commit()
        profile_id = profile.id
    app = FastAPI()
    app.include_router(server_routes.router)
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            with (
                patch.object(server_routes, "fetch_tailnet_status", AsyncMock(side_effect=env.fake.tailnet)),
                patch.object(server_routes, "_probe_many_via_bridge", AsyncMock(side_effect=env.fake.probe)),
            ):
                viewer = {"Authorization": f"Bearer {create_access_token(f'test-servers-{tag}')}"}
                denied = {"Authorization": f"Bearer {create_access_token(f'test-noperm-{tag}')}"}
                for headers in (admin_headers, viewer):
                    resp = await c.get("/api/v1/servers/readiness", headers=headers)
                    assert resp.status_code == 200, resp.text
                    entry = next(e for e in resp.json()["entries"] if e["server_id"] == str(machine.id))
                    assert entry["status"] == "complete"
                    assert datetime.fromisoformat(entry["status_since"]) == env.day
                assert (await c.get("/api/v1/servers/readiness", headers=denied)).status_code == 403
    finally:
        server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.username.in_([f"test-servers-{tag}", f"test-noperm-{tag}"])))
            await db.execute(delete(ProfilePermission).where(ProfilePermission.profile_id == profile_id))
            await db.execute(delete(Profile).where(Profile.id == profile_id))
            await db.commit()
