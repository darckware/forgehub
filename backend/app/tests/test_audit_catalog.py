"""The persisted checklist and Athos verifier must share one stable ID set."""

from pathlib import Path

import pytest

from app.core.audit_catalog import (
    CANONICAL_AUDIT_CHECKS,
    RETIRED_AUDIT_CHECKS,
    verifier_check_names,
)

VERIFIER = Path("/root/.hermes/profiles/athos/scripts/checklist_verifier.py")


def test_catalog_v2_ids_are_contiguous_and_unique():
    expected = {f"ECO-{number:03d}" for number in range(1, 59)}
    assert set(CANONICAL_AUDIT_CHECKS) | set(RETIRED_AUDIT_CHECKS) == expected
    assert len(CANONICAL_AUDIT_CHECKS) == 57
    assert {name for name, check in CANONICAL_AUDIT_CHECKS.items() if not check.enabled} == {
        "ECO-048", "ECO-050", "ECO-055", "ECO-056", "ECO-058"
    }
    assert all(
        check.activation_condition
        for check in CANONICAL_AUDIT_CHECKS.values() if not check.enabled
    )


def test_retired_ids_are_never_reused():
    assert set(CANONICAL_AUDIT_CHECKS).isdisjoint(RETIRED_AUDIT_CHECKS)
    assert set(RETIRED_AUDIT_CHECKS) == {"ECO-021"}


def test_catalog_matches_verifier():
    if not VERIFIER.exists():
        pytest.skip("Athos verifier is unavailable on this host")
    assert verifier_check_names(VERIFIER.read_text()) == set(CANONICAL_AUDIT_CHECKS)


def test_verifier_parser_does_not_execute_source():
    source = "raise RuntimeError('executed')\nCHECKS = {'ECO-042': lambda: None}\n"
    assert verifier_check_names(source) == {"ECO-042"}


def test_new_checks_have_bounded_commands_and_owners():
    for number in range(42, 59):
        name = f"ECO-{number:03d}"
        check = CANONICAL_AUDIT_CHECKS[name]
        assert check.name == name
        assert check.agent_profile
        assert check.category
        assert check.description
        assert 1 <= check.timeout_seconds <= 600


@pytest.mark.asyncio
async def test_db_catalog_matches_canonical():
    """Run after applying the catalogue migration to a test database."""
    from sqlalchemy import select

    from app.db.models.audit import AuditCheck
    from app.db.base import AsyncSessionLocal

    async with AsyncSessionLocal() as db_session:
        rows = (await db_session.execute(select(AuditCheck.name, AuditCheck.enabled))).all()
    by_name = dict(rows)
    if not set(CANONICAL_AUDIT_CHECKS).issubset(by_name):
        pytest.skip("Catalog migration has not been applied to this test database")
    assert all(by_name[name] is spec.enabled for name, spec in CANONICAL_AUDIT_CHECKS.items())
    assert by_name["ECO-021"] is False
