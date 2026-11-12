"""Machine status monitor: alerts when a machine leaves `complete`, and when it
comes back (Remote Access support plan phase 4, gap 10, Marcelo 2026-11-12).

`run_machine_status_pass` is called every 15 minutes by `main.py`'s
`_machine_status_poll_loop` (never under ENVIRONMENT=test, where every loop is
off). It reads machines through `compute_readiness` -- the very computation
behind `GET /servers/readiness`, including its 5-minute SSH probe cache, so the
monitor never adds a login burst on client workstations -- and compares each
enabled machine's status with the last one recorded in
`machine_status_observations`.

Rules:
- A machine's first observation only records the baseline. If the very first
  pass (no machine observed yet) finds machines already off `complete`, it
  creates ONE summary notification, deduped per day.
- An alert (warning) when a machine moves from `complete` to anything else, or
  into offline/not_prepared/unknown from any other state -- debounced: a
  degrade seen once waits in `pending_status` and is recorded (and alerted,
  with the instant it was first seen) only if the next pass still sees it.
  A "voltou" (info) on the first pass back at `complete`. Other moves
  (offline -> partial) are only recorded. The event key carries the
  transition instant, so offline -> back -> offline alerts twice, and a
  restart re-alerts nothing.
- Mass guard: when one pass confirms degrades for at least `MASS_DEGRADE_MIN`
  machines, or more than half of those in scope (never for one machine),
  the transitions are recorded with `mass_batch` and ONE summary is sent
  (likely the probe, ForgeVault or the VPS's network, e.g. the bridge
  answering `not_installed` for every vault-key machine). Their recoveries
  are grouped the same way: one summary, not one "voltou" each.
- Never a false alarm: when a source is unreadable as a whole (the VPS isn't
  `online` in the tailnet while some machine depends on it, or the SSH probe
  bridge didn't answer), the pass records no transition at all -- previous
  states are kept, no "voltou" either -- and emits one "monitoramento
  indisponível" notice per day. A per-machine `unknown` from a readable
  source is real (still debounced).
- Only machines with access enabled; a disabled machine's observation is
  dropped, so re-enabling it starts a fresh (silent) baseline. A machine
  deleted mid-pass is skipped. Unregistered tailnet devices never appear
  (readiness reads only `servers` rows).
- Readiness is read with no transaction open; the advisory lock (one pass at
  a time even with two backends on one database) is taken only to write.
- The "Motivo:" line is pt-BR from `READINESS_DETAIL_PT`; no translation, no line.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.machine_status import MachineStatusObservation
from app.db.models.notification import Notification

logger = logging.getLogger(__name__)

MACHINE_STATUS_POLL_SECONDS = 15 * 60
# Any constant distinct from other advisory locks: two backends sharing one
# database (dev.sh --prod-db beside production) must not both alert.
_PASS_LOCK_KEY = 0x6D616368  # "mach"

DEGRADED_STATUSES = ("offline", "not_prepared", "unknown")
# A pass degrading at least this many machines (or more than half of those in
# scope) sends one summary instead of one alert per machine.
MASS_DEGRADE_MIN = 5
STATUS_LABELS = {
    "complete": "completo",
    "partial": "parcial",
    "not_prepared": "não preparada",
    "offline": "offline",
    "unknown": "desconhecido",
}
SCREEN_HINT = "Veja em Acesso remoto (/remote-access)."


@dataclass
class MachineStatusPassResult:
    skipped: bool = False
    source_unavailable: bool = False
    baselined: int = 0
    changed: int = 0
    pending: int = 0  # degrades seen once, waiting for confirmation
    mass_degrade: bool = False
    alerts: list[str] = field(default_factory=list)  # event keys created


def _label(server) -> str:
    client = (server.darckware_client_name or "").strip()
    return f"{server.name} ({client})" if client else server.name


def _status(value: str) -> str:
    return STATUS_LABELS.get(value, value)


async def _notify(
    db: AsyncSession, result: MachineStatusPassResult, *, key: str, severity: str, title: str, message: str,
    now: datetime,
) -> None:
    exists = (await db.execute(select(Notification.id).where(Notification.event_key == key))).scalar_one_or_none()
    if exists is not None:
        return
    db.add(
        Notification(
            source="system", severity=severity, title=title[:255], message=message,
            event_key=key, occurred_at=now,
        )
    )
    result.alerts.append(key)


def transition_kind(previous: str, current: str) -> str | None:
    """"degraded", "recovered" or None (recorded silently). Pure."""
    if previous == current:
        return None
    if current == "complete":
        return "recovered"
    if previous == "complete" or current in DEGRADED_STATUSES:
        return "degraded"
    return None


def is_mass_degrade(degraded: int, in_scope: int) -> bool:
    """Many machines degrading in the same pass is more likely the probe,
    ForgeVault or the VPS's network than the machines. One machine is never
    a mass. Pure."""
    return degraded >= 2 and (degraded >= MASS_DEGRADE_MIN or degraded * 2 > in_scope)


def _reason_pt(detail: str | None) -> str | None:
    from app.api.routes.server import READINESS_DETAIL_PT

    return READINESS_DETAIL_PT.get(detail or "")


def _names(items, limit: int = 20) -> str:
    names = ", ".join(items[:limit])
    if len(items) > limit:
        names += f" e mais {len(items) - limit}"
    return names


async def run_machine_status_pass(
    db: AsyncSession, *, now: datetime | None = None, server_ids: Collection[uuid.UUID] | None = None
) -> MachineStatusPassResult:
    """One monitoring pass; commits. `server_ids` limits the pass to those
    machines (tests share a database with other rows).

    Readiness is read first, with no transaction open across the tailnet read
    and the SSH probe; only then is the advisory lock taken, the machines and
    observations re-read and the result written."""
    from app.api.routes.server import compute_readiness
    from app.db.models.server import Server

    now = now or datetime.now(timezone.utc)
    result = MachineStatusPassResult()
    snap = await compute_readiness(db, release_transaction=True)

    locked = (await db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _PASS_LOCK_KEY})).scalar()
    if not locked:
        result.skipped = True
        await db.rollback()
        return result

    machines = [m for m in snap.machines if server_ids is None or m.server.id in server_ids]
    # Re-read the rows under a key-share lock: a machine deleted meanwhile is
    # skipped, and one deleted from now on waits for this commit instead of
    # failing the whole pass on the foreign key.
    present = dict(
        (
            await db.execute(
                select(Server.id, Server.access_enabled)
                .where(Server.id.in_([m.server.id for m in machines]))
                .with_for_update(key_share=True)
            )
        ).all()
    ) if machines else {}
    machines = [m for m in machines if m.server.id in present]
    disabled = [m.server.id for m in machines if not (m.server.access_enabled and present[m.server.id])]
    scope = [m for m in machines if m.server.access_enabled and present[m.server.id]]
    if disabled:
        await db.execute(delete(MachineStatusObservation).where(MachineStatusObservation.server_id.in_(disabled)))

    # The tailnet is readable only when the VPS itself is online in it
    # (needs_login/offline/starting can't tell whether a peer is offline).
    tailnet_down = snap.tailnet.server.state != "online" and any(m.server.tailnet_node_id for m in scope)
    if scope and (tailnet_down or snap.ssh_probe_failed):
        result.source_unavailable = True
        which = "a tailnet" if tailnet_down else "a sondagem SSH (ponte do host)"
        if tailnet_down and snap.ssh_probe_failed:
            which = "a tailnet e a sondagem SSH (ponte do host)"
        await _notify(
            db, result, key=f"machine-status-unavailable:{now.date().isoformat()}", severity="warning",
            title="Monitoramento das máquinas indisponível",
            message=(
                f"Não foi possível ler {which}. Os estados das máquinas foram mantidos até a próxima "
                f"leitura; nenhum alerta foi gerado. {SCREEN_HINT}"
            ),
            now=now,
        )
        await db.commit()
        return result

    ids = [m.server.id for m in scope]
    observed = {
        o.server_id: o
        for o in (
            await db.execute(select(MachineStatusObservation).where(MachineStatusObservation.server_id.in_(ids)))
        ).scalars()
    } if ids else {}
    first_pass = not observed
    baseline_off = []
    degrades = []  # (machine, observation, old status, transition instant)
    recoveries = []  # (machine, old status, recorded by a mass degrade)
    for m in scope:
        server, current = m.server, m.status
        obs = observed.get(server.id)
        if obs is None:
            db.add(MachineStatusObservation(server_id=server.id, status=current, since=now, last_checked_at=now))
            result.baselined += 1
            if current != "complete":
                baseline_off.append(m)
            continue
        obs.last_checked_at = now
        if obs.status == current:
            obs.pending_status = obs.pending_since = None
            continue
        kind = transition_kind(obs.status, current)
        if kind == "degraded":
            if obs.pending_status is None:
                # Seen once: wait for the next pass before believing it.
                obs.pending_status, obs.pending_since = current, now
                result.pending += 1
            else:
                degrades.append((m, obs, obs.status, obs.pending_since or now))
            continue
        old, was_mass = obs.status, obs.mass_batch
        obs.status, obs.since, obs.mass_batch = current, now, False
        obs.pending_status = obs.pending_since = None
        result.changed += 1
        if kind == "recovered":
            recoveries.append((m, old, was_mass))

    mass = is_mass_degrade(len(degrades), len(scope))
    for m, obs, old, since in degrades:
        obs.status, obs.since, obs.mass_batch = m.status, since, mass
        obs.pending_status = obs.pending_since = None
        result.changed += 1
        if mass:
            continue
        reason = _reason_pt(m.detail or m.status_detail)
        await _notify(
            db, result, key=f"machine-status:{m.server.id}:{m.status}:{since.isoformat()}", severity="warning",
            title=f"Máquina {_status(m.status)}: {_label(m.server)}",
            message=(
                f"{_label(m.server)} passou de {_status(old)} para {_status(m.status)}."
                + (f" Motivo: {reason}." if reason else "")
                + f" {SCREEN_HINT}"
            ),
            now=now,
        )
    if mass:
        result.mass_degrade = True
        count = len(degrades)
        names = _names([f"{_label(m.server)} ({_status(old)} → {_status(m.status)})" for m, _o, old, _s in degrades])
        await _notify(
            db, result, key=f"machine-status-mass:{now.isoformat()}", severity="warning",
            title=f"{count} máquinas mudaram de estado ao mesmo tempo",
            message=(
                f"{count} máquinas mudaram de estado ao mesmo tempo — possível falha da sondagem, do "
                f"ForgeVault ou da rede da VPS: {names}. {SCREEN_HINT}"
            ),
            now=now,
        )

    batch_back = [(m, old) for m, old, was_mass in recoveries if was_mass]
    for m, old, was_mass in recoveries:
        if was_mass:
            continue
        await _notify(
            db, result, key=f"machine-status:{m.server.id}:complete:{now.isoformat()}", severity="info",
            title=f"Máquina voltou: {_label(m.server)}",
            message=f"{_label(m.server)} voltou ao estado completo (estava {_status(old)}). {SCREEN_HINT}",
            now=now,
        )
    if batch_back:
        count = len(batch_back)
        await _notify(
            db, result, key=f"machine-status-mass-recovered:{now.isoformat()}", severity="info",
            title=(
                f"Máquina voltou: {_label(batch_back[0][0].server)}"
                if count == 1
                else f"{count} máquinas voltaram ao estado completo"
            ),
            message=(
                "Voltaram ao estado completo depois de uma mudança em massa: "
                f"{_names([_label(m.server) for m, _old in batch_back])}. {SCREEN_HINT}"
            ),
            now=now,
        )

    if first_pass and baseline_off:
        count = len(baseline_off)
        names = _names([f"{_label(m.server)} ({_status(m.status)})" for m in baseline_off])
        await _notify(
            db, result, key=f"machine-status-summary:{now.date().isoformat()}", severity="warning",
            title=f"{count} máquina{'s' if count != 1 else ''} fora do estado completo",
            message=f"Primeira leitura do monitoramento: {names}. {SCREEN_HINT}",
            now=now,
        )
    await db.commit()
    return result
