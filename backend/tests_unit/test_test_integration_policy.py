"""Plano Integrado T.3: under ENVIRONMENT=test every integration goes to the
stub or is refused, no real URL or credential is accepted, and a client's or
production host is refused.

No database and no network: every outgoing HTTP request is intercepted and
answered by the stub app in-process, a socket connect fails the test, and
"production" is a fixture file of invented values. Runs with --noconftest
and with ENVIRONMENT=test:

    pytest --noconftest tests_unit/test_test_integration_policy.py
    ENVIRONMENT=test pytest tests_unit/test_test_integration_policy.py
"""
from __future__ import annotations

import json
import os
import secrets
import socket
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import HTTPException

from app.core import config
from app.core import test_integration_policy as policy
from app.core.config import Settings
from app.core.test_integration_policy import UnsafeTestConfigurationError

STUB_HOST = "http://127.0.0.1:8003"
STUB_IN_NETWORK = "http://forgehub_test_stubs:8900"

#: Invented "production" values; the policy must recognize them by hash.
FAKE_PRODUCTION = {
    "JWT_SECRET": "prod-jwt-" + "a" * 40,
    "CHAT_BRIDGE_TOKEN": "prod-bridge-" + "b" * 40,
    "AGENT_ACTIVITY_WEBHOOK_SECRET": "prod-webhook-" + "c" * 40,
    "DARCKWARE_APPROVER_TOKEN": "prod-approver-" + "d" * 40,
    "POSTGRES_PASSWORD": "prod-db-" + "e" * 40,
    "FORGEROUTER_API_KEY": "sk-fr-prod-" + "f" * 40,
}

#: Every setting named in the task, with a production or client value it
#: must refuse. Hosts/addresses are the real production names or invented
#: client/tailnet addresses; nothing here is ever dialed.
REAL_TARGETS = [
    ("CHAT_BRIDGE_URL", "http://host.docker.internal:8910"),
    ("CHAT_BRIDGE_URL", "http://172.17.0.1:8910"),
    ("CHAT_BRIDGE_URL", "http://forgehub_test_stubs:8910"),
    ("DARCKWARE_API_URL", "http://darckware-backend:8020"),
    ("DARCKWARE_API_URL", "https://darckware.net"),
    ("DARCKWARE_API_URL", "https://portal.darckware.net/api"),
    ("FORGEROUTER_URL", "http://forgerouter:2100"),
    ("FORGEROUTER_URL", "http://127.0.0.1:2100"),
    ("TAILSCALE_API_URL", "https://api.tailscale.com/api/v2"),
    ("WEATHER_API_URL", "https://api.open-meteo.com/v1/forecast"),
    ("WEATHER_REVERSE_GEOCODE_URL", "https://nominatim.openstreetmap.org/reverse"),
    # A client's LAN host and a tailnet address.
    ("CHAT_BRIDGE_URL", "http://172.15.2.4:8910"),
    ("DARCKWARE_API_URL", "http://100.101.102.103:8020"),
    # Even a fictitious address is not the stub.
    ("FORGEROUTER_URL", "http://192.0.2.10:2100"),
    # Credentials smuggled in the URL.
    ("CHAT_BRIDGE_URL", "http://user:pass@127.0.0.1:8003"),
]


def _token() -> str:
    return secrets.token_hex(32)


def _test_values(origin: str = STUB_HOST) -> dict[str, object]:
    return {
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": 5439,
        "POSTGRES_DB": "forgehub_test", "POSTGRES_USER": "forgehub_test", "POSTGRES_PASSWORD": _token(),
        "JWT_SECRET": _token(), "CHAT_BRIDGE_TOKEN": _token(), "SECRETS_ENCRYPTION_KEY": _token(),
        "AGENT_ACTIVITY_WEBHOOK_SECRET": _token(),
        "DARCKWARE_AGENT_TOKEN": _token(), "DARCKWARE_APPROVER_TOKEN": _token(),
        "FORGEROUTER_TEST_API_KEY": policy.FORGEROUTER_TEST_KEY_PREFIX + _token(),
        "DARCKWARE_AGENT_TOKEN_FILE": "", "RECAPTCHA_SECRET_KEY": "", "FORGEROUTER_SSO_SECRET": "",
        "CHAT_BRIDGE_URL": origin,
        "DARCKWARE_API_URL": f"{origin}/darckware",
        "FORGEROUTER_URL": f"{origin}/forgerouter",
        "TAILSCALE_API_URL": f"{origin}/tailscale",
        "WEATHER_API_URL": f"{origin}/weather",
        "WEATHER_REVERSE_GEOCODE_URL": f"{origin}/weather",
    }


@pytest.fixture
def production_env(tmp_path, monkeypatch) -> Path:
    """A fake production .env as the reference, and no hash file."""
    env = tmp_path / "prod.env"
    env.write_text("".join(f"{k}={v}\n" for k, v in FAKE_PRODUCTION.items()) + "DEV_USER_PASSWORD=admin\n")
    monkeypatch.setattr(config, "PRODUCTION_ENV_FILE", env)
    monkeypatch.setattr(config, "PRODUCTION_SECRET_HASH_FILE", tmp_path / "missing-hashes")
    return env


def build(**overrides) -> Settings:
    values = _test_values()
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _assert_no_secret_in(message: str) -> None:
    for value in FAKE_PRODUCTION.values():
        assert value not in message


# --- configuration ---------------------------------------------------------------


@pytest.mark.parametrize("origin", [STUB_HOST, STUB_IN_NETWORK, "http://localhost:8003"])
def test_stub_configuration_is_accepted(production_env, origin):
    s = build(**_test_values(origin))
    for name, (_, prefix) in policy.INTEGRATION_URL_SETTINGS.items():
        assert getattr(s, name).rstrip("/") == f"{origin}{prefix}"


def test_empty_integration_url_is_accepted_as_a_refusal(production_env):
    s = build(CHAT_BRIDGE_URL="", DARCKWARE_API_URL="", FORGEROUTER_URL="")
    assert s.CHAT_BRIDGE_URL == "" and s.DARCKWARE_API_URL == ""


@pytest.mark.parametrize("name,url", REAL_TARGETS)
def test_real_or_client_target_is_refused(production_env, name, url):
    with pytest.raises(UnsafeTestConfigurationError) as exc:
        build(**{name: url})
    assert name in str(exc.value)
    assert "user:pass" not in str(exc.value)  # a URL's userinfo is never echoed


def test_stub_origin_with_another_integrations_prefix_is_refused(production_env):
    with pytest.raises(UnsafeTestConfigurationError, match="DARCKWARE_API_URL"):
        build(DARCKWARE_API_URL=f"{STUB_HOST}/forgerouter")


def test_code_defaults_are_refused_under_test(production_env):
    """ENVIRONMENT=test with nothing else set: production URLs, default JWT."""
    with pytest.raises(UnsafeTestConfigurationError) as exc:
        Settings(_env_file=None, ENVIRONMENT="test", POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=5439,
                 POSTGRES_DB="forgehub_test", POSTGRES_USER="forgehub_test",
                 **{k: "" for k in ("CHAT_BRIDGE_TOKEN", "SECRETS_ENCRYPTION_KEY", "AGENT_ACTIVITY_WEBHOOK_SECRET",
                                    "DARCKWARE_AGENT_TOKEN_FILE", "RECAPTCHA_SECRET_KEY")})
    message = str(exc.value)
    for name in ("CHAT_BRIDGE_URL", "DARCKWARE_API_URL", "FORGEROUTER_URL", "TAILSCALE_API_URL", "JWT_SECRET"):
        assert name in message


@pytest.mark.parametrize("name", list(policy.REQUIRED_TEST_SECRETS))
@pytest.mark.parametrize("value", ["", "change-me", "dev_only_insecure_jwt_secret_change_me", "short"])
def test_required_credential_unset_default_or_short_is_refused(production_env, name, value):
    if value == "dev_only_insecure_jwt_secret_change_me" and name != "JWT_SECRET":
        value = ""  # only JWT_SECRET has that default; the others default to empty
    with pytest.raises(UnsafeTestConfigurationError, match=name):
        build(**{name: value})


@pytest.mark.parametrize("name,prod_key", [
    ("JWT_SECRET", "JWT_SECRET"),
    ("CHAT_BRIDGE_TOKEN", "CHAT_BRIDGE_TOKEN"),
    ("AGENT_ACTIVITY_WEBHOOK_SECRET", "AGENT_ACTIVITY_WEBHOOK_SECRET"),
    # Production derives its encryption key from JWT_SECRET.
    ("SECRETS_ENCRYPTION_KEY", "JWT_SECRET"),
    # Across keys too: a production token reused as another test credential.
    ("CHAT_BRIDGE_TOKEN", "DARCKWARE_APPROVER_TOKEN"),
    ("DARCKWARE_APPROVER_TOKEN", "DARCKWARE_APPROVER_TOKEN"),
    ("DARCKWARE_AGENT_TOKEN", "CHAT_BRIDGE_TOKEN"),
    ("POSTGRES_PASSWORD", "POSTGRES_PASSWORD"),
])
def test_production_credential_is_refused_without_showing_it(production_env, name, prod_key):
    with pytest.raises(UnsafeTestConfigurationError) as exc:
        build(**{name: FAKE_PRODUCTION[prod_key]})
    message = str(exc.value)
    assert f"{name} is equal to a production secret ({prod_key}" in message
    _assert_no_secret_in(message)


def test_production_reference_from_hash_file_only(tmp_path, monkeypatch, production_env):
    """The containers have no .env: the hash file init-env.sh writes is the reference."""
    salt, hashes = policy.production_secret_hashes_from_env(production_env)
    hash_file = tmp_path / ".prod-secret-hashes"
    hash_file.write_text(json.dumps({"salt": salt, "hashes": hashes}))
    assert all(v not in hash_file.read_text() for v in FAKE_PRODUCTION.values())
    assert "DEV_USER_PASSWORD" not in hashes  # too short to be worth a hash
    monkeypatch.setattr(config, "PRODUCTION_ENV_FILE", tmp_path / "no-env")
    monkeypatch.setattr(config, "PRODUCTION_SECRET_HASH_FILE", hash_file)
    build()
    with pytest.raises(UnsafeTestConfigurationError, match="CHAT_BRIDGE_TOKEN is equal to a production secret"):
        build(CHAT_BRIDGE_TOKEN=FAKE_PRODUCTION["CHAT_BRIDGE_TOKEN"])


def test_no_production_reference_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION_ENV_FILE", tmp_path / "no-env")
    monkeypatch.setattr(config, "PRODUCTION_SECRET_HASH_FILE", tmp_path / "no-hashes")
    with pytest.raises(UnsafeTestConfigurationError, match="no production reference"):
        build()


def test_repeated_test_credential_is_refused(production_env):
    shared = _token()
    with pytest.raises(UnsafeTestConfigurationError, match="each test credential needs its own value"):
        build(JWT_SECRET=shared, SECRETS_ENCRYPTION_KEY=shared)


@pytest.mark.parametrize("override,setting", [
    ({"DARCKWARE_AGENT_TOKEN_FILE": "/root/.config/forgevault/lara-darckware-token"}, "DARCKWARE_AGENT_TOKEN_FILE"),
    ({"RECAPTCHA_SECRET_KEY": "x" * 40}, "RECAPTCHA_SECRET_KEY"),
    ({"WEATHER_ENABLED": True, "WEATHER_API_URL": ""}, "WEATHER_ENABLED"),
])
def test_other_real_sources_are_refused(production_env, override, setting):
    with pytest.raises(UnsafeTestConfigurationError, match=setting):
        build(**override)


def test_policy_does_not_apply_outside_test(production_env):
    s = Settings(_env_file=None, ENVIRONMENT="production", CHAT_BRIDGE_URL="http://host.docker.internal:8910")
    assert s.CHAT_BRIDGE_URL == "http://host.docker.internal:8910"


@pytest.mark.parametrize("host,fictitious", [
    ("192.0.2.10", True), ("198.51.100.7", True), ("203.0.113.250", True), ("srv-teste.test", True),
    ("operador@192.0.2.11:22", True),
    ("172.15.2.4", False), ("100.101.102.103", False), ("10.0.0.5", False), ("8.8.8.8", False),
    ("srv-sup", False), ("forgehub.darckware.net", False), ("host.docker.internal", False), ("", False),
])
def test_fictitious_host(host, fictitious):
    assert policy.is_fictitious_host(host) is fictitious


def test_encryption_key_is_independent_from_jwt_secret(production_env, monkeypatch):
    from app.core import secrets as app_secrets

    s = build()
    monkeypatch.setattr(config.settings, "JWT_SECRET", s.JWT_SECRET)
    monkeypatch.setattr(config.settings, "SECRETS_ENCRYPTION_KEY", s.SECRETS_ENCRYPTION_KEY)
    ciphertext = app_secrets.encrypt_secret("fictitious-value")
    monkeypatch.setattr(config.settings, "SECRETS_ENCRYPTION_KEY", "")  # production derivation
    with pytest.raises(ValueError):
        app_secrets.decrypt_secret(ciphertext)


@pytest.mark.skipif(not config.is_test_environment(os.environ.get("ENVIRONMENT")), reason="ENVIRONMENT=test only")
def test_this_process_settings_point_at_the_stub():
    """The real settings this process loaded (test-env/.env.test)."""
    for name in policy.INTEGRATION_URL_SETTINGS:
        assert policy.integration_url_problem(name, getattr(config.settings, name)) is None
        value = getattr(config.settings, name)
        assert not value or (urlsplit(value).hostname, urlsplit(value).port) in {
            (h, p) for _, h, p in policy.STUB_ORIGINS}


# --- every integration call lands on the stub ----------------------------------------


@pytest.fixture
def stubbed(tmp_path, monkeypatch, production_env):
    """The shared `settings` set to a validated test configuration, every
    outgoing httpx request answered by the stub app in-process, and any real
    socket connect turned into a failure."""
    from app.tests.fixtures import integration_stub

    s = build()
    for name in (*policy.INTEGRATION_URL_SETTINGS, *policy.REQUIRED_TEST_SECRETS, "DARCKWARE_AGENT_TOKEN",
                 "DARCKWARE_APPROVER_TOKEN", "DARCKWARE_AGENT_TOKEN_FILE", "FORGEROUTER_TEST_API_KEY"):
        monkeypatch.setattr(config.settings, name, getattr(s, name))
    monkeypatch.setattr(integration_stub, "LOG_PATH", tmp_path / "calls.jsonl")
    seen: list[str] = []
    asgi = httpx.ASGITransport(app=integration_stub.app)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        origin = (request.url.scheme, request.url.host, request.url.port)
        seen.append(f"{origin[0]}://{origin[1]}:{origin[2]}")
        assert origin in policy.STUB_ORIGINS, f"request left for {origin}"
        return await asgi.handle_async_request(request)

    def no_connect(*args, **kwargs):
        raise AssertionError(f"real socket connect attempted: {args[1:]}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    monkeypatch.setattr(socket.socket, "connect", no_connect)
    return SimpleNamespace(settings=s, seen=seen, stub=integration_stub, log=tmp_path / "calls.jsonl")


def _calls(stubbed) -> list[dict]:
    return stubbed.stub.read_calls()


async def test_telegram_reply_goes_to_the_stub(stubbed):
    from app.core import feedback

    demand = SimpleNamespace(channel_ref="999000111", from_agent_id=None, target_agent_id=None, number=9001,
                             subject="Fictitious", dispatch_status="completed", dispatch_error=None,
                             dispatch_result="private reply text")
    assert await feedback._deliver_telegram(None, demand) is True
    [call] = _calls(stubbed)
    assert call["integration"] == "host-bridge" and call["operation"] == "message.send.telegram"
    assert call["destination"] == "telegram:999000111" and call["outcome"] == "stubbed" and call["auth"] == "test"
    assert "private reply text" not in stubbed.log.read_text()


async def test_client_email_and_darckware_go_to_the_stub(stubbed):
    from app.core import darckware_client as dw

    clients = await dw.request("GET", "/clients", params={"limit": 100})
    assert {c["company_name"] for c in clients["items"]} == {"Cliente Fictício Alfa Ltda", "Cooperativa Fictícia Beta"}
    email = await dw.request("POST", "/outbound-emails", json={
        "to_email": "contato@cliente-alfa.test", "kind": "geral", "subject": "Assunto", "body_text": "corpo confidencial"})
    assert email["status"] == "aguardando_aprovacao"
    approved = await dw.request("POST", f"/outbound-emails/{email['id']}/approve", credential="approver",
                                json={"version": 1, "body_hash": email["body_hash"]})
    assert approved["status"] == "aprovado"
    ops = [(c["operation"], c["destination"], c["auth"]) for c in _calls(stubbed)]
    assert ("email.queue", "contato@cliente-alfa.test", "test") in ops
    assert ("email.approve", "contato@cliente-alfa.test", "test") in ops
    assert "corpo confidencial" not in stubbed.log.read_text()


async def test_production_token_is_answered_unauthorized(stubbed, monkeypatch):
    """A request carrying a non-test token never gets a working answer."""
    from app.core import darckware_client as dw

    # The stub shares this process' settings, so only the client side changes.
    monkeypatch.setattr(dw, "_token", lambda credential: FAKE_PRODUCTION["DARCKWARE_APPROVER_TOKEN"])
    with pytest.raises(HTTPException) as exc:
        await dw.request("GET", "/clients")
    assert exc.value.detail["code"] == "darckware_credential"
    assert _calls(stubbed)[-1]["auth"] == "rejected"
    assert FAKE_PRODUCTION["DARCKWARE_APPROVER_TOKEN"] not in stubbed.log.read_text()


async def test_agent_dispatch_goes_to_the_stub(stubbed):
    import uuid

    from app.core.agent_runs import dispatch_agent_run, poll_agent_run

    agent = SimpleNamespace(name="Agente Teste", runtime_type="hermes", profile_slug="agente-teste",
                            autonomous_runs=False, id=uuid.uuid4())
    run_id = str(uuid.uuid4())
    started = await dispatch_agent_run(run_id, agent, "secret prompt text", "/srv/teste")
    assert started["status"] == "running"
    finished = await poll_agent_run(run_id)
    assert finished["status"] == "completed" and finished["output"].endswith("STATUS: DONE")
    assert [c["operation"] for c in _calls(stubbed)] == ["agent_run.start", "agent_run.get"]
    assert "secret prompt text" not in stubbed.log.read_text()


async def test_forgevault_is_refused(stubbed):
    from app.core import forgevault

    with pytest.raises(forgevault.VaultUnavailable):
        await forgevault._bridge("secrets:reveal-by-name", {"name": "RUSTDESK_SERVER"})
    assert _calls(stubbed)[-1]["integration"] == "forgevault" and _calls(stubbed)[-1]["outcome"] == "refused"


async def test_forgerouter_goes_to_the_stub(stubbed, monkeypatch):
    from app.core import forgerouter_llm

    async def test_key(db, slug):
        return config.settings.FORGEROUTER_TEST_API_KEY

    monkeypatch.setattr(forgerouter_llm, "agent_api_key", test_key)
    reply = await forgerouter_llm.chat(None, "lara", "forgerouter/standard", [{"role": "user", "content": "texto"}])
    assert "test stub" in reply
    assert _calls(stubbed)[-1] == {**_calls(stubbed)[-1], "integration": "forgerouter", "auth": "test"}


@pytest.mark.parametrize("presented,auth", [
    (FAKE_PRODUCTION["FORGEROUTER_API_KEY"], "rejected"),  # a production key
    ("qualquer-chave", "rejected"),  # anything non-empty, as the old check accepted
    (policy.FORGEROUTER_TEST_KEY_PREFIX + "0" * 64, "rejected"),  # right prefix, not the test key
    (None, "missing"),
])
async def test_forgerouter_refuses_any_key_but_the_test_one(stubbed, presented, auth):
    headers = {"Authorization": f"Bearer {presented}"} if presented else {}
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{config.settings.FORGEROUTER_URL}/v1/chat/completions",
                                 json={"model": "forgerouter/standard", "messages": []}, headers=headers)
        accepted = await client.post(
            f"{config.settings.FORGEROUTER_URL}/v1/chat/completions", json={"model": "forgerouter/standard"},
            headers={"Authorization": f"Bearer {config.settings.FORGEROUTER_TEST_API_KEY}"})
    assert resp.status_code == 401
    assert accepted.status_code == 200
    rejected, ok = _calls(stubbed)
    assert (rejected["outcome"], rejected["auth"]) == ("unauthorized", auth)
    assert (ok["outcome"], ok["auth"]) == ("stubbed", "test")
    log = stubbed.log.read_text()
    assert config.settings.FORGEROUTER_TEST_API_KEY not in log
    if presented:
        assert presented not in log


async def test_forgerouter_test_key_without_prefix_is_rejected(stubbed, monkeypatch):
    """Even when it equals the configured value, a key without the frtest_
    prefix is not a test key (a settings validated elsewhere can't widen it)."""
    unprefixed = _token()
    monkeypatch.setattr(config.settings, "FORGEROUTER_TEST_API_KEY", unprefixed)
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{config.settings.FORGEROUTER_URL}/v1/chat/completions", json={},
                                 headers={"Authorization": f"Bearer {unprefixed}"})
    assert resp.status_code == 401 and _calls(stubbed)[-1]["auth"] == "rejected"


async def test_forgerouter_without_a_test_key_refuses_everything(stubbed, monkeypatch):
    monkeypatch.setattr(config.settings, "FORGEROUTER_TEST_API_KEY", "")
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{config.settings.FORGEROUTER_URL}/v1/chat/completions", json={},
                                 headers={"Authorization": f"Bearer {policy.FORGEROUTER_TEST_KEY_PREFIX}{_token()}"})
    assert resp.status_code == 401 and _calls(stubbed)[-1]["auth"] == "rejected"


async def test_agents_use_the_test_forgerouter_key_under_test(monkeypatch):
    """Under ENVIRONMENT=test no agent key is read from ForgeRouter's registry
    or the database copy: every agent uses FORGEROUTER_TEST_API_KEY."""
    from app.core import forgerouter_llm, forgerouter_sync

    agent = SimpleNamespace(name="Agente Teste", forgerouter_api_key_encrypted="never-decrypted")

    class _Db:
        async def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: agent))

    async def registry():
        raise AssertionError("ForgeRouter's registry read under test")

    key = policy.FORGEROUTER_TEST_KEY_PREFIX + _token()
    monkeypatch.setattr(forgerouter_sync, "read_forgerouter_agent_keys", registry)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(config.settings, "FORGEROUTER_TEST_API_KEY", key)
    assert await forgerouter_llm.agent_api_key(_Db(), "agente-teste") == key
    monkeypatch.setattr(config.settings, "FORGEROUTER_TEST_API_KEY", "")
    with pytest.raises(forgerouter_llm.LlmError) as exc:
        await forgerouter_llm.agent_api_key(_Db(), "agente-teste")
    assert exc.value.kind == "not_configured"


@pytest.mark.parametrize("value", ["", policy.FORGEROUTER_TEST_KEY_PREFIX + _token()])
def test_forgerouter_test_key_convention_is_accepted(production_env, value):
    assert build(FORGEROUTER_TEST_API_KEY=value).FORGEROUTER_TEST_API_KEY == value


@pytest.mark.parametrize("value", ["change-me", _token(), policy.FORGEROUTER_TEST_KEY_PREFIX + "curta",
                                   FAKE_PRODUCTION["FORGEROUTER_API_KEY"]])
def test_forgerouter_test_key_off_convention_is_refused(production_env, value):
    with pytest.raises(UnsafeTestConfigurationError) as exc:
        build(FORGEROUTER_TEST_API_KEY=value)
    assert "FORGEROUTER_TEST_API_KEY" in str(exc.value)
    assert value not in str(exc.value)


def test_forgerouter_test_key_equal_to_production_is_refused(production_env):
    """A production key that happens to carry the prefix is still refused by hash."""
    prod_like = policy.FORGEROUTER_TEST_KEY_PREFIX + "9" * 40
    production_env.write_text(production_env.read_text() + f"FORGEROUTER_API_KEY_2={prod_like}\n")
    with pytest.raises(UnsafeTestConfigurationError) as exc:
        build(FORGEROUTER_TEST_API_KEY=prod_like)
    assert "equal to a production secret" in str(exc.value) and prod_like not in str(exc.value)


@pytest.mark.parametrize("credential,token,auth", [
    ("agent", lambda: config.settings.DARCKWARE_APPROVER_TOKEN, "rejected"),  # the other credential's token
    ("approver", lambda: config.settings.DARCKWARE_AGENT_TOKEN, "rejected"),
    ("agent", lambda: FAKE_PRODUCTION["DARCKWARE_APPROVER_TOKEN"], "rejected"),
    ("agent", lambda: "", "missing"),
])
async def test_darckware_accepts_only_the_paths_own_test_token(stubbed, credential, token, auth):
    value = token()
    headers = {"Authorization": f"Bearer {value}"} if value else {}
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{config.settings.DARCKWARE_API_URL}/api/internal/{credential}/clients",
                                headers=headers)
    assert resp.status_code == 401
    assert (_calls(stubbed)[-1]["outcome"], _calls(stubbed)[-1]["auth"]) == ("unauthorized", auth)
    if value:
        assert value not in stubbed.log.read_text()


@pytest.mark.parametrize("presented,expected,prefix,result", [
    ("abc", "abc", "", "test"),
    ("abc", "abd", "", "rejected"),
    ("abc", "", "", "rejected"),  # no test credential configured: nothing is accepted
    (None, "abc", "", "missing"),
    ("frtest_x", "frtest_x", "frtest_", "test"),
    ("x", "x", "frtest_", "rejected"),
])
def test_check_test_credential(presented, expected, prefix, result):
    assert policy.check_test_credential(presented, expected, prefix=prefix) == result


async def test_tailscale_is_refused(stubbed):
    from app.core import tailscale_api

    with pytest.raises(HTTPException) as exc:
        await tailscale_api.create_auth_key("tskey-api-fictitious", "tag:teste", "teste")
    assert exc.value.status_code == 502
    assert _calls(stubbed)[-1] == {**_calls(stubbed)[-1], "integration": "tailscale", "outcome": "refused"}


@pytest.mark.parametrize("path,body,expected", [
    ("/v1/servers/exec", {"host": "192.0.2.11", "user": "operador", "command": "true"}, 200),
    ("/v1/servers/exec", {"host": "172.15.2.4", "user": "darckware", "command": "true"}, 403),
    ("/v1/servers/check-status", {"servers": [{"id": "a", "ip_address": "192.0.2.10", "remote_user": "x"},
                                              {"id": "b", "ip_address": "100.101.102.103", "remote_user": "x"}]}, 403),
    ("/v1/servers/detect-os", {"host": "srv-teste.test"}, 200),
    ("/v1/exec", {"command": "id"}, 403),
    ("/v1/fs/list", {"path": "/root"}, 403),
    ("/v1/remote-fs/list", {"path": "/", "server": {"host": "192.0.2.10"}}, 403),
    ("/v1/forgevault/secrets:reveal-by-name", {"name": "X"}, 403),
])
async def test_host_bridge_surface(stubbed, path, body, expected):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{config.settings.CHAT_BRIDGE_URL}{path}", json=body,
                                 headers={"X-Bridge-Token": config.settings.CHAT_BRIDGE_TOKEN})
    assert resp.status_code == expected, resp.text
    if expected == 403:
        assert "forgehub test stub" in resp.json()["detail"]


async def test_wrong_bridge_token_is_unauthorized(stubbed):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{config.settings.CHAT_BRIDGE_URL}/v1/messages/send",
                                 json={"target": "telegram:1", "message": "x"},
                                 headers={"X-Bridge-Token": FAKE_PRODUCTION["CHAT_BRIDGE_TOKEN"]})
    assert resp.status_code == 401
    assert _calls(stubbed)[-1]["outcome"] == "unauthorized"
    assert FAKE_PRODUCTION["CHAT_BRIDGE_TOKEN"] not in stubbed.log.read_text()


async def test_stub_calls_are_listed(stubbed):
    async with httpx.AsyncClient() as client:
        await client.post(f"{config.settings.CHAT_BRIDGE_URL}/v1/messages/send",
                          json={"target": "telegram:42", "message": "olá"},
                          headers={"X-Bridge-Token": config.settings.CHAT_BRIDGE_TOKEN})
        listed = (await client.get(f"{STUB_HOST}/_stub/calls", params={"integration": "host-bridge"})).json()
    assert listed["total"] == 1 and listed["calls"][0]["destination"] == "telegram:42"
    assert set(listed["calls"][0]) == {"at", "integration", "method", "path", "operation", "destination",
                                       "outcome", "status", "auth"}


async def test_evidence_probes_answer_only_for_fictitious_roots(stubbed):
    """M0.6a: the completion guard's file/git probes reach the stub, which
    answers only for fictitious roots and records every call."""
    from app.core import evidence_bridge

    root = stubbed.stub.STUB_EVIDENCE_ROOT + "app"
    integrated, pending = list(stubbed.stub.STUB_COMMITS)
    assert await evidence_bridge.verify_on_host("git", root, integrated[:12], None) == (True, "commit exists (stub)")
    assert (await evidence_bridge.verify_on_host("git", root, "deadbeefdeadbeef", None))[0] is False
    assert (await evidence_bridge.verify_on_host("file", root, "README.md", None))[0] is True
    assert (await evidence_bridge.verify_on_host("file", root, "nope.md", None))[0] is False
    assert (await evidence_bridge.commit_is_integrated(root, integrated, "develop"))[0] is True
    assert (await evidence_bridge.commit_is_integrated(root, pending, "develop"))[0] is False
    for real_root in ("/root/project/forgehub", "/srv/forgehub-test/../../root"):
        with pytest.raises(evidence_bridge.EvidenceUnverifiable):
            await evidence_bridge.verify_on_host("file", real_root, "README.md", None)
    calls = [c for c in _calls(stubbed) if c["operation"] in ("evidence.verify", "git.is_ancestor")]
    assert len(calls) == 8
    assert [c["outcome"] for c in calls[-2:]] == ["refused", "refused"]
    assert all(c["auth"] == "test" for c in calls)
