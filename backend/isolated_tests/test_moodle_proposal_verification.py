import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.moodle_proposal_verification import ProposalInvalid, validate_proposal


def proposal():
    p = {"request_id": "b7fa75cf-056e-46c0-8de4-954131b7d6ba", "wsfunction": "core_user_delete_users",
         "params": {"userids": [12]}, "environment": "staging", "host": "https://example.test",
         "status": "pending", "destructive": True,
         "created_at": datetime.now(timezone.utc).isoformat(),
         "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
    p["params_hash"] = hashlib.sha256(json.dumps([p["wsfunction"], p["params"], p["environment"], p["host"]],
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return p


def test_checks_real_contents_and_rejects_modified_parameters():
    p = proposal()
    assert validate_proposal(p, p["request_id"])["params_hash"] == p["params_hash"]
    p["params"]["userids"] = [13]
    with pytest.raises(ProposalInvalid):
        validate_proposal(p, p["request_id"])


@pytest.mark.parametrize("field,value", [("wsfunction", "core_course_delete_modules"),
    ("status", "approved"), ("destructive", False), ("expires_at", "2020-01-01T00:00:00Z"),
    ("request_id", "wrong")])
def test_rejects_untrusted_proposal(field, value):
    p = proposal()
    p[field] = value
    with pytest.raises(ProposalInvalid):
        validate_proposal(p, "b7fa75cf-056e-46c0-8de4-954131b7d6ba")


def test_rejects_ambiguous_javascript_numbers():
    p = proposal()
    p["params"] = {"x": 1.5}
    with pytest.raises(ProposalInvalid):
        validate_proposal(p, p["request_id"])


@pytest.mark.parametrize("function,destructive", [("core_course_delete_courses", True),
    ("core_group_delete_groups", True), ("core_course_update_courses", False)])
def test_accepts_new_explicit_functions(function, destructive):
    p = proposal()
    p.update(wsfunction=function, destructive=destructive)
    p["params_hash"] = hashlib.sha256(json.dumps([function, p["params"], p["environment"], p["host"]],
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert validate_proposal(p, p["request_id"])["wsfunction"] == function


def test_non_ascii_hash_is_invalid():
    p = proposal()
    p["params_hash"] = "é"
    with pytest.raises(ProposalInvalid):
        validate_proposal(p, p["request_id"])


def test_untrusted_function_type_is_rejected():
    p = proposal()
    p["wsfunction"] = []
    with pytest.raises(ProposalInvalid):
        validate_proposal(p, p["request_id"])


def test_rejects_extended_ttl():
    p = proposal()
    p["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with pytest.raises(ProposalInvalid):
        validate_proposal(p, p["request_id"])
