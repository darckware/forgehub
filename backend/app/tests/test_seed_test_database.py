"""Fictitious test seed (Plano Integrado T.2, app/scripts/seed_test_database.py).

The pure tests and the guard test need no database (they run with
`--noconftest`). The last test seeds the test database twice: the seed is
that database's baseline (`test-env/reset.sh --seed`), so its rows are left
in place on purpose -- seeding merges by fixed primary key and never
duplicates.
"""
import ipaddress
import json
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from app.scripts import seed_test_database as seed_module

BACKEND_DIR = Path(__file__).resolve().parents[2]
DOCUMENTATION_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
# Names of the real ecosystem (agents, owner, clients' systems): none may
# appear anywhere in the seed.
REAL_NAMES = (
    "athos", "atlas", "aegis", "porthus", "aramis", "dartan", "maia", "lara", "kairos", "hephaestus",
    "scriba", "themis", "daedalus", "mnemosyne", "marcelo", "semed", "darckware", "coreti", "duplica",
)


def _all_strings(row) -> list[str]:
    return [v for k, v in vars(row).items() if not k.startswith("_") and isinstance(v, str) and k != "hashed_password"]


def test_ids_are_deterministic_and_derived_from_the_seed_namespace():
    first = [(type(r).__name__, r.id) for r in seed_module.build_rows()]
    second = [(type(r).__name__, r.id) for r in seed_module.build_rows()]
    assert first == second
    assert len({rid for _, rid in first}) == len(first)
    for _, rid in first:
        assert isinstance(rid, uuid.UUID) and rid.version == 5


def test_seed_covers_every_required_entity():
    kinds = {type(r).__name__ for r in seed_module.build_rows()}
    assert {"Product", "ProductVersion", "Project", "PlanningItem", "ProjectTask", "Agent", "User", "Server"} <= kinds
    rows = seed_module.build_rows()
    assert any(type(r).__name__ == "User" and r.is_admin and r.username == seed_module.TEST_ADMIN_USERNAME for r in rows)
    assert any(type(r).__name__ == "Server" and r.kind == "workstation" for r in rows)
    assert any(type(r).__name__ == "Product" and r.darckware_client_id for r in rows)  # clients


def test_seed_is_fictitious():
    for row in seed_module.build_rows():
        name = type(row).__name__
        if name == "Server":
            assert any(ipaddress.ip_address(row.ip_address) in net for net in DOCUMENTATION_NETS), row.ip_address
            assert row.ssh_key_path is None and row.private_key_encrypted is None
            assert row.login_password_ref is None and row.rustdesk_id is None
        if name == "User":
            assert row.email.endswith(".test")
        if name == "Agent":
            assert row.forgerouter_api_key_encrypted is None and row.home_path is None
        for value in _all_strings(row):
            lowered = value.lower()
            assert not any(real in lowered for real in REAL_NAMES), f"{name}: {value!r}"


_RUNNER = textwrap.dedent(
    """
    import json, runpy, socket, sys
    attempts = []
    def _blocked(self, address, *args):
        attempts.append(repr(address))
        raise OSError("connection blocked by the seed guard test")
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    code = 0
    try:
        runpy.run_module("app.scripts.seed_test_database", run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    print("SEED_RESULT " + json.dumps({"code": code, "connects": attempts}))
    """
)


@pytest.mark.parametrize("environment", ["test", "production"])
def test_seed_refuses_production_target_without_connecting(environment):
    env = {k: v for k, v in os.environ.items() if not k.startswith("POSTGRES_") and k != "ENVIRONMENT"}
    env.update({
        "ENVIRONMENT": environment, "POSTGRES_HOST": "forgehub_postgres", "POSTGRES_PORT": "5433",
        "POSTGRES_DB": "forgehub", "POSTGRES_USER": "foundation", "POSTGRES_PASSWORD": "not-a-real-password",
    })
    proc = subprocess.run([sys.executable, "-c", _RUNNER], cwd=BACKEND_DIR, env=env,
                          capture_output=True, text=True, timeout=120)
    line = next(l for l in proc.stdout.splitlines() if l.startswith("SEED_RESULT "))
    result = json.loads(line.removeprefix("SEED_RESULT "))
    assert result["code"] == 2, proc.stdout + proc.stderr
    assert "refused:" in proc.stderr
    assert result["connects"] == []


@pytest.mark.asyncio
async def test_seeding_twice_gives_identical_rows():
    from app.core.config import settings

    first = await seed_module.seed(settings)
    second = await seed_module.seed(settings)
    assert first == second

    from sqlalchemy import select
    from app.db.base import AsyncSessionLocal
    from app.db.models.product import Product
    from app.db.models.task import ProjectTask

    expected_products = {seed_module.seed_id("products", p[0]) for p in seed_module.PRODUCTS}
    async with AsyncSessionLocal() as db:
        found = set((await db.execute(select(Product.id).where(Product.id.in_(expected_products)))).scalars())
        numbers = set((await db.execute(select(ProjectTask.number).where(ProjectTask.number >= 9001))).scalars())
    assert found == expected_products
    assert {9001, 9008} <= numbers
