"""Guard that keeps tests off production databases (Plano Integrado T.1).

Pure unit tests: none of them needs a database, so they run with
`--noconftest` as well as inside the suite. The conftest cases spawn a
fresh pytest with socket connects intercepted, so "the session aborts" and
"no connection was opened" are both observed, not assumed. Every production-
shaped target here uses the container name `forgehub_postgres`, which does
not resolve outside foundation_network, and a bogus password -- even a
broken guard could not reach production from these tests.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.core import config
from app.core.config import (
    Settings,
    UnsafeDatabaseTargetError,
    assert_test_database_target,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_TARGET = dict(host="127.0.0.1", port=5439, database="forgehub_test", user="forgehub_test")
PRODUCTION_ENV = {
    "POSTGRES_HOST": "forgehub_postgres",
    "POSTGRES_PORT": "5433",
    "POSTGRES_DB": "forgehub",
    "POSTGRES_USER": "foundation",
    "POSTGRES_PASSWORD": "not-a-real-password",
}


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "LOCALHOST "])
def test_allowlisted_target_passes(host):
    assert_test_database_target(host, 5439, "forgehub_test", "forgehub_test")


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"port": 5433}, "port 5433 is production"),
        ({"host": "forgehub_postgres"}, "host 'forgehub_postgres' is production"),
        ({"database": "forgehub"}, "database 'forgehub' is production"),
        ({"user": "foundation"}, "user 'foundation' is production"),
        # Not production by name, still refused: allowlist, not denylist.
        ({"port": 5432}, "not on the test allowlist"),
        ({"host": "hindsight_postgres"}, "not on the test allowlist"),
        ({"port": 55439}, "not on the test allowlist"),
        ({"database": "forgehub_test2"}, "not on the test allowlist"),
    ],
)
def test_target_off_allowlist_is_refused(override, reason):
    target = {**TEST_TARGET, **override}
    with pytest.raises(UnsafeDatabaseTargetError, match=reason):
        assert_test_database_target(target["host"], target["port"], target["database"], target["user"])


def test_settings_refuse_production_in_test_environment():
    with pytest.raises(UnsafeDatabaseTargetError):
        _settings(ENVIRONMENT="test")  # field defaults are production's
    with pytest.raises(UnsafeDatabaseTargetError, match="port 5433"):
        _settings(
            ENVIRONMENT=" Test ",
            POSTGRES_HOST="127.0.0.1",
            POSTGRES_PORT=5433,
            POSTGRES_DB="forgehub",
            POSTGRES_USER="forgehub_test",
        )


def test_settings_accept_test_target_and_leave_production_alone():
    _settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5439,
        POSTGRES_DB="forgehub_test",
        POSTGRES_USER="forgehub_test",
    )
    # Outside ENVIRONMENT=test the guard is inert: production keeps working.
    assert _settings(ENVIRONMENT="production").POSTGRES_PORT == 5433


def test_refusal_never_includes_the_password():
    with pytest.raises(UnsafeDatabaseTargetError) as excinfo:
        _settings(ENVIRONMENT="test", POSTGRES_PASSWORD="s3cret-value")
    assert "s3cret-value" not in str(excinfo.value)


def test_secondary_database_urls_are_refused_in_test():
    test_settings = _settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5439,
        POSTGRES_DB="forgehub_test",
        POSTGRES_USER="forgehub_test",
    )
    with pytest.raises(UnsafeDatabaseTargetError):
        test_settings.db_url_for("hindsight_postgres", 5432, "hindsight")
    with pytest.raises(UnsafeDatabaseTargetError):
        test_settings.db_url_for("forgerouter_postgres", 5432, "forgerouter", user="proxyrouter_user")


def test_test_environment_never_loads_the_production_env_file(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    files = config._env_files()
    assert str(config._ENV_FILE) not in files
    assert files[-1] == str(config.TEST_ENV_FILE)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert str(config._ENV_FILE) in config._env_files()


# Runs pytest in a fresh interpreter with every socket connect recorded and
# refused, then reports both the exit code and whether anything connected.
_RUNNER = textwrap.dedent(
    """
    import json, socket, sys
    attempts = []
    def _blocked(self, address, *args):
        attempts.append(repr(address))
        raise OSError("connection blocked by the guard test")
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    import pytest
    code = pytest.main(sys.argv[1:])
    print("GUARD_RESULT " + json.dumps({"code": int(code), "connects": attempts}))
    """
)


def _run_suite_with(env_overrides: dict[str, str]) -> tuple[int, list[str], str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("POSTGRES_") and k != "ENVIRONMENT"}
    env.update(env_overrides)
    proc = subprocess.run(
        [
            sys.executable, "-c", _RUNNER, "-q", "-p", "no:cacheprovider",
            "app/tests/test_test_database_guard.py::test_allowlisted_target_passes",
        ],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120,
    )
    output = proc.stdout + proc.stderr
    line = next(l for l in proc.stdout.splitlines() if l.startswith("GUARD_RESULT "))
    result = json.loads(line.removeprefix("GUARD_RESULT "))
    return result["code"], result["connects"], output


def test_conftest_aborts_session_on_production_target_without_connecting():
    code, connects, output = _run_suite_with({"ENVIRONMENT": "test", **PRODUCTION_ENV})
    assert code == 4, output
    assert "Test database guard" in output and "port 5433 is production" in output
    assert connects == []


def test_conftest_aborts_session_outside_test_environment_without_connecting():
    code, connects, output = _run_suite_with({"ENVIRONMENT": "production", **PRODUCTION_ENV})
    assert code == 4, output
    assert "runs only with ENVIRONMENT=test" in output
    assert connects == []
