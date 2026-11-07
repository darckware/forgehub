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
