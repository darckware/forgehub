"""ECO-060: the verdict on what ForgeVault's audit returned, and its refusal to pass blind."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

SPEC = importlib.util.spec_from_file_location(
    "eco060_audit", Path(__file__).resolve().parents[1] / "forgevault_ssh_key_audit.py")
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def data(**overrides):
    base = {"audit_rows": 100, "scanned": 4, "key_secrets": 7, "allowed_accounts": 1,
            "allowed_reads": 4, "unclassified": 0, "findings": []}
    return base | overrides


def finding(identity="porthus", secret="WS_A_SSH_KEY", reads=3):
    return {"identity": identity, "secret": secret, "reads": reads,
            "last_read": "2026-11-07T10:00:00Z"}


def test_only_the_allowed_identity_passes():
    code, notes = audit.evaluate(data())
    assert code == audit.EXIT_OK
    assert "4 read(s) scanned" in notes


def test_another_identity_fails_with_the_four_fields():
    code, notes = audit.evaluate(data(findings=[finding()]))
    assert code == audit.EXIT_FOUND
    assert "identity=porthus secret=WS_A_SSH_KEY count=3 last=2026-11-07T10:00:00Z" in notes


@pytest.mark.parametrize("overrides", [
    {"allowed_accounts": 0}, {"key_secrets": 0}, {"audit_rows": 0}, {"unclassified": 1},
])
def test_nothing_to_judge_is_not_verified(overrides):
    code, notes = audit.evaluate(data(**overrides))
    assert code == audit.EXIT_NOT_VERIFIED
    assert notes.startswith("NOT VERIFIED")


def test_a_finding_outranks_an_unclassified_read():
    code, notes = audit.evaluate(data(findings=[finding()], unclassified=2))
    assert code == audit.EXIT_FOUND
    assert "2 other read(s) could not be classified" in notes


def test_long_output_says_how_much_it_left_out():
    rows = [finding(secret=f"WS_{number:04d}_SSH_KEY") for number in range(500)]
    code, notes = audit.evaluate(data(findings=rows))
    assert code == audit.EXIT_FOUND
    assert len(notes) < 4000
    assert "1500 read(s)" in notes
    assert "more identity/secret pair(s) omitted" in notes


@pytest.mark.parametrize("outcome", [
    subprocess.CompletedProcess([], 1, "", "connection refused"),
    subprocess.CompletedProcess([], 0, "not json", ""),
    subprocess.CompletedProcess([], 0, "{}", ""),
    FileNotFoundError("docker"),
    subprocess.TimeoutExpired("docker", 40),
])
def test_unreadable_audit_never_passes(monkeypatch, capsys, outcome):
    def run(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(audit.subprocess, "run", run)
    assert audit.main() == audit.EXIT_NOT_VERIFIED
    output = capsys.readouterr().out
    assert output.startswith("NOT VERIFIED")
    assert "connection refused" not in output


def test_query_has_no_row_limit_and_selects_no_value():
    query = audit.QUERY.lower()
    assert "limit" not in query
    assert "secret_versions" not in query
    assert "metadata" not in query


KEY_NAMES = {
    "WS_C_M_SSH_KEY": True,                      # original name
    "WS_C_M_SSH_KEY_20261101120000_ABCD1234": True,  # rotated before 2026-11-12: suffix after
    "WS_C_M_0A1B2C3D4E5F_SSH_KEY": True,         # since 2026-11-12: suffix before the purpose
    "ws_c_m_ssh_key": True,
    "WS_C_M_LOGIN": False,
    "WS_C_M_SSHKEY": False,
    "RUSTDESK_SERVER": False,
    "X_SSH_KEYS": False,
    "X_SSH_KEY_PASSPHRASE": False,
    "WS_C_M_SSH_KEY_ABCD1234": False,             # not the old rotation suffix
}

PREDICATE = "~ '_SSH_KEY(_[0-9]{14}_[0-9A-F]{8})?$'"


def test_every_key_secret_name_is_matched_not_only_a_suffix():
    """Rotated secrets keep their old `..._SSH_KEY_<suffix>` names, so the
    query must match `_SSH_KEY` anywhere, in both places it classifies names."""
    query = audit.QUERY
    assert "right(upper(" not in query and "strpos(" not in query
    assert query.count(f"upper(secret_name) {PREDICATE}") == 1
    assert query.count(f"upper(name) {PREDICATE}") == 1


def test_plural_and_passphrase_names_are_not_keys():
    """`_SSH_KEY` must end the name or be followed by exactly the suffix old
    rotations appended (`_<YYYYMMDDHHMMSS>_<8 HEX>`), nothing else."""
    import re
    pattern = re.compile(PREDICATE.split("'")[1])
    for name, is_key in KEY_NAMES.items():
        assert bool(pattern.search(name.upper())) is is_key, name


def test_the_name_predicate_on_a_real_postgres():
    """Same predicate, evaluated by Postgres (the isolated test instance, a
    SELECT of literals only). Skipped where that container isn't running."""
    import shutil
    if not shutil.which("docker"):
        pytest.skip("docker not available")
    values = ", ".join(f"('{name}')" for name in KEY_NAMES)
    sql = f"SELECT name, upper(name) {PREDICATE} FROM (VALUES {values}) AS t(name)"
    result = subprocess.run(
        ["docker", "exec", "-i", "forgehub_test_postgres", "psql", "-X", "-At", "-F", "|",
         "-U", "forgehub_test", "-d", "forgehub_test", "-c", sql],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        pytest.skip("isolated test Postgres not reachable")
    got = {name: flag == "t" for name, flag in (line.split("|") for line in result.stdout.split())}
    assert got == KEY_NAMES


def test_acknowledged_reads_are_exact_row_ids():
    assert len(audit.ACKNOWLEDGED_READS) == 7
    assert len(set(audit.ACKNOWLEDGED_READS)) == 7
    for row_id in audit.ACKNOWLEDGED_READS:
        assert len(row_id) == 36 and row_id.count("-") == 4
    assert "NOT acknowledged GROUP BY" in audit.QUERY


def test_ok_reports_how_many_acknowledged_reads_it_left_out():
    code, notes = audit.evaluate(data(acknowledged_reads=7))
    assert code == audit.EXIT_OK
    assert "7 read(s) acknowledged by Marcelo left out" in notes
