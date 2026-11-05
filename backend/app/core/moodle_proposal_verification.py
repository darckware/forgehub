"""Validate the same proposal snapshot Moodle signs before trusting it.

The deliberately restricted JSON domain avoids Python/JavaScript number and
Unicode ordering differences; unsupported proposals must fail closed.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone


DESTRUCTIVE_FUNCTIONS = frozenset({
    "enrol_manual_unenrol_users", "core_group_delete_group_members", "core_user_delete_users",
    "core_course_delete_courses", "core_group_delete_groups",
})
ALLOWED_FUNCTIONS = DESTRUCTIVE_FUNCTIONS | {
    "core_course_update_courses", "core_user_create_users", "core_group_create_groups",
    "enrol_manual_enrol_users", "core_group_add_group_members", "core_user_update_users",
}


class ProposalInvalid(ValueError):
    pass


def _canonical(value):
    if value is None or isinstance(value, bool):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, int) and abs(value) <= 9007199254740991:
        return str(value)
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProposalInvalid("Unsupported string") from exc
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        try:
            keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        except UnicodeEncodeError as exc:
            raise ProposalInvalid("Unsupported key") from exc
        return "{" + ",".join(_canonical(k) + ":" + _canonical(value[k]) for k in keys) + "}"
    raise ProposalInvalid("Unsupported proposal parameter")


def validate_proposal(proposal, request_id):
    if not isinstance(proposal, dict) or proposal.get("request_id") != request_id:
        raise ProposalInvalid("Unknown proposal")
    function = proposal.get("wsfunction")
    if not isinstance(function, str) or function not in ALLOWED_FUNCTIONS or proposal.get("destructive") is not (function in DESTRUCTIVE_FUNCTIONS):
        raise ProposalInvalid("Operation is not permitted")
    if function == "core_user_update_users":
        params = proposal.get("params")
        if not isinstance(params, dict) or set(params) != {"standard_password_reset"}:
            raise ProposalInvalid("Only standard password reset descriptors are permitted")
        reset = params["standard_password_reset"]
        if (not isinstance(reset, dict) or set(reset) != {"userid", "date_of_birth", "policy"}
                or type(reset["userid"]) is not int or not 0 < reset["userid"] <= 9007199254740991
                or reset["policy"] != "semed_birthdate_v1"
                or not isinstance(reset["date_of_birth"], str)
                or not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", reset["date_of_birth"])):
            raise ProposalInvalid("Invalid standard password reset descriptor")
        try:
            birth_date = datetime.strptime(reset["date_of_birth"], "%d/%m/%Y").date()
            if birth_date.year < 1000 or birth_date > datetime.now(timezone.utc).date():
                raise ValueError
        except ValueError as exc:
            raise ProposalInvalid("Invalid birth date") from exc
    if proposal.get("status") != "pending" or not isinstance(proposal.get("params"), dict):
        raise ProposalInvalid("Proposal is not pending")
    if function == "core_user_create_users":
        # A password in a proposal would rest in a file; the MCP derives it after the claim.
        users = proposal["params"].get("users")
        if not isinstance(users, list) or any(not isinstance(u, dict) or "password" in u for u in users):
            raise ProposalInvalid("A create proposal cannot carry a password")
    if not all(isinstance(proposal.get(k), str) and proposal[k] for k in ("host", "environment", "params_hash", "created_at", "expires_at")):
        raise ProposalInvalid("Proposal is incomplete")
    if re.fullmatch(r"[0-9a-f]{64}", proposal["params_hash"]) is None:
        raise ProposalInvalid("Invalid proposal hash")
    try:
        expires = datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00"))
        created = datetime.fromisoformat(proposal["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if (expires.tzinfo is None or created.tzinfo is None or expires <= now or created > now
                or expires <= created or expires > created + timedelta(hours=24)):
            raise ProposalInvalid("Proposal expired")
    except ValueError as exc:
        raise ProposalInvalid("Invalid expiry") from exc
    material = [proposal["wsfunction"], proposal["params"], proposal["environment"], proposal["host"]]
    digest = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(digest, proposal["params_hash"]):
        raise ProposalInvalid("Proposal integrity mismatch")
    return proposal
