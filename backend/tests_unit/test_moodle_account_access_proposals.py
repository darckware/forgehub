"""ForgeHub accepts the MCP's suspension and account-confirmation proposals in exactly one shape
each; anything wider (another field, a second user, a repeated id) fails closed."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.moodle_proposal_verification import ProposalInvalid, _canonical, validate_proposal


def proposal(wsfunction, params):
    now = datetime.now(timezone.utc)
    data = {"request_id": str(uuid.uuid4()), "wsfunction": wsfunction, "params": params, "destructive": False,
            "status": "pending", "environment": "staging", "host": "moodle.test:9443",
            "created_at": (now - timedelta(minutes=1)).isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat()}
    material = [wsfunction, params, data["environment"], data["host"]]
    data["params_hash"] = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    return data


@pytest.mark.parametrize("flag", [0, 1])
def test_a_suspension_of_one_user_is_accepted(flag):
    data = proposal("core_user_update_users", {"users": [{"id": 11, "suspended": flag}]})
    assert validate_proposal(data, data["request_id"]) is data


@pytest.mark.parametrize("params", [
    {"users": [{"id": 11, "suspended": 1, "email": "x@example.test"}]},
    {"users": [{"id": 11, "suspended": 1, "password": "x"}]},
    {"users": [{"id": 11, "suspended": 1}, {"id": 12, "suspended": 1}]},
    {"users": [{"id": 11, "suspended": True}]},
    {"users": [{"id": 11, "suspended": 2}]},
    {"users": [{"id": 0, "suspended": 1}]},
    {"users": [{"id": 11, "firstname": "Outro"}]},
])
def test_any_other_user_update_is_refused(params):
    data = proposal("core_user_update_users", params)
    with pytest.raises(ProposalInvalid):
        validate_proposal(data, data["request_id"])


def test_an_account_confirmation_is_accepted():
    data = proposal("local_moodle_accounts_confirm_users", {"userids": [30, 31, 32, 33, 34]})
    assert validate_proposal(data, data["request_id"]) is data


@pytest.mark.parametrize("params", [
    {"userids": []},
    {"userids": list(range(1, 32))},
    {"userids": [30, 30]},
    {"userids": [30, "31"]},
    {"userids": [30], "notify": True},
    {"users": [30]},
])
def test_a_wider_account_confirmation_is_refused(params):
    data = proposal("local_moodle_accounts_confirm_users", params)
    with pytest.raises(ProposalInvalid):
        validate_proposal(data, data["request_id"])


def test_a_confirmation_marked_destructive_or_changed_after_the_hash_is_refused():
    data = proposal("local_moodle_accounts_confirm_users", {"userids": [30]})
    data["destructive"] = True
    with pytest.raises(ProposalInvalid):
        validate_proposal(data, data["request_id"])
    data = proposal("local_moodle_accounts_confirm_users", {"userids": [30]})
    data["params"]["userids"].append(31)
    with pytest.raises(ProposalInvalid, match="integrity"):
        validate_proposal(data, data["request_id"])
