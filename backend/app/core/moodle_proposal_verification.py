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
    "mcp_student_batch_v1", "local_moodle_accounts_confirm_users",
}
STUDENT_BATCH_FUNCTION = "mcp_student_batch_v1"
# The Moodle plugin local_moodle_accounts (moodle repo, moodle-local-accounts/): core has no
# Web Service that confirms an account.
CONFIRM_USERS_FUNCTION = "local_moodle_accounts_confirm_users"
CONFIRM_USERS_MAX = 30
STUDENT_BATCH_MAX_ROWS = 30
MAX_SAFE_INT = 9007199254740991


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


def _positive_id(value):
    return type(value) is int and 0 < value <= MAX_SAFE_INT


def _text(value, limit=254):
    return isinstance(value, str) and 0 < len(value) <= limit


def _birth_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", value):
        raise ProposalInvalid("Invalid birth date")
    try:
        birth_date = datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ProposalInvalid("Invalid birth date") from exc
    if birth_date.year < 1000 or birth_date > datetime.now(timezone.utc).date():
        raise ProposalInvalid("Invalid birth date")


def _no_password(value):
    """A password would rest in a file: the MCP derives it after the claim."""
    if isinstance(value, dict):
        for key, item in value.items():
            if "password" in key.lower() and key != "standard_password":
                raise ProposalInvalid("A batch proposal cannot carry a password")
            _no_password(item)
    elif isinstance(value, list):
        for item in value:
            _no_password(item)
    elif isinstance(value, str) and "@semed" in value.lower():
        raise ProposalInvalid("A batch proposal cannot carry a password")


def _is_suspension(params):
    """The MCP's moodle_propose_set_user_suspension: one user, only `suspended` as 0 or 1."""
    if not isinstance(params, dict) or set(params) != {"users"}:
        return False
    users = params["users"]
    return (isinstance(users, list) and len(users) == 1 and isinstance(users[0], dict)
            and set(users[0]) == {"id", "suspended"} and _positive_id(users[0]["id"])
            and type(users[0]["suspended"]) is int and users[0]["suspended"] in (0, 1))


def _candidates(value):
    return isinstance(value, list) and all(
        isinstance(c, dict) and set(c) == {"id", "username"} and _positive_id(c["id"]) and _text(c["username"])
        for c in value)


def _batch_row(row):
    if not isinstance(row, dict) or not _positive_id(row.get("row")) or row.get("action") not in ("create", "existing"):
        raise ProposalInvalid("Invalid batch row")
    target = row.get("enrolment")
    if target is not None and (
            not isinstance(target, dict)
            or set(target) != {"courseid", "course_shortname", "roleid", "role_shortname", "groupid", "group_name"}
            or not all(_positive_id(target[k]) for k in ("courseid", "roleid", "groupid"))
            or not _text(target["course_shortname"]) or not _text(target["group_name"])
            or target["role_shortname"] != "student"):
        raise ProposalInvalid("Invalid batch destination")
    if row["action"] == "existing":
        if set(row) != {"row", "action", "enrolment", "userid", "username", "full_name"} or target is None \
                or not _positive_id(row["userid"]) or not _text(row["username"]):
            raise ProposalInvalid("Invalid existing student row")
        return
    allowed = {"row", "action", "enrolment", "full_name", "account", "corrected_fields", "possible_duplicate_of"}
    account = row.get("account")
    if (not set(row) <= allowed or not isinstance(account, dict)
            or set(account) != {"username", "firstname", "lastname", "email", "auth", "standard_password"}
            or account["auth"] != "manual" or not _text(row.get("full_name"))
            or not all(_text(account[k], 100) for k in ("firstname", "lastname"))
            or f"{account['firstname']} {account['lastname']}" != row["full_name"]
            or not isinstance(account["username"], str)
            or re.fullmatch(r"[a-z0-9][a-z0-9_.@-]{1,99}", account["username"]) is None
            or account["email"] != f"{account['username']}@gmail.com"):
        raise ProposalInvalid("Invalid new student row")
    standard = account["standard_password"]
    if not isinstance(standard, dict) or set(standard) != {"date_of_birth", "policy"} or standard["policy"] != "semed_birthdate_v1":
        raise ProposalInvalid("Invalid password policy")
    _birth_date(standard["date_of_birth"])
    if "possible_duplicate_of" in row and not _candidates(row["possible_duplicate_of"]):
        raise ProposalInvalid("Invalid duplicate warning")
    corrected = row.get("corrected_fields", [])
    if not isinstance(corrected, list) or not set(corrected) <= {"firstname", "lastname", "username", "email"}:
        raise ProposalInvalid("Invalid correction flag")


def _validate_student_batch(params):
    batch = params.get("student_batch")
    if set(params) != {"student_batch"} or not isinstance(batch, dict) \
            or set(batch) != {"version", "rows", "held_rows", "rejected_rows"} or batch["version"] != 1:
        raise ProposalInvalid("Invalid student batch")
    rows, held, left = batch["rows"], batch["held_rows"], batch["rejected_rows"]
    if not isinstance(rows, list) or not 0 < len(rows) <= STUDENT_BATCH_MAX_ROWS or not isinstance(held, list) or not isinstance(left, list):
        raise ProposalInvalid("Invalid student batch size")
    _no_password(batch)
    for row in rows:
        _batch_row(row)
    for row in held:
        if (not isinstance(row, dict) or set(row) != {"row", "full_name", "candidates"} or not _positive_id(row["row"])
                or not _text(row["full_name"]) or not _candidates(row["candidates"])):
            raise ProposalInvalid("Invalid held row")
    for row in left:
        if (not isinstance(row, dict) or set(row) != {"row", "label", "code", "reason"} or not _positive_id(row["row"])
                or not all(isinstance(row[k], str) for k in ("label", "code", "reason"))):
            raise ProposalInvalid("Invalid rejected row")
    numbers = [row["row"] for row in rows + held + left]
    usernames = [row["account"]["username"] for row in rows if row["action"] == "create"]
    if len(set(numbers)) != len(numbers) or len(set(usernames)) != len(usernames):
        raise ProposalInvalid("Repeated row in student batch")


def student_batch_view(params):
    """What a person checks before approving. Built from the hashed params, never from the free
    summary text, and without the birth date, which only the MCP needs."""
    batch = params["student_batch"]
    rows = []
    for row in batch["rows"]:
        account, target = row.get("account") or {}, row.get("enrolment") or {}
        rows.append({"row": row["row"], "action": row["action"], "full_name": row.get("full_name"),
            "firstname": account.get("firstname"), "lastname": account.get("lastname"),
            "username": account.get("username") or row.get("username"), "email": account.get("email"),
            "userid": row.get("userid"), "course": target.get("course_shortname"), "group": target.get("group_name"),
            "account_only": not target, "corrected_fields": row.get("corrected_fields", []),
            "possible_duplicate_of": row.get("possible_duplicate_of", [])})
    groups = sorted({row["group"] for row in rows if row["group"]})
    return {"total": len(rows), "new_accounts": sum(row["action"] == "create" for row in rows),
        "existing": sum(row["action"] == "existing" for row in rows), "account_only": sum(row["account_only"] for row in rows),
        "units": sorted({name.split(" - ")[0] for name in groups if " - " in name}),
        "courses": sorted({row["course"] for row in rows if row["course"]}), "groups": groups,
        "rows": rows, "held_rows": batch["held_rows"], "rejected_rows": batch["rejected_rows"]}


def validate_proposal(proposal, request_id):
    if not isinstance(proposal, dict) or proposal.get("request_id") != request_id:
        raise ProposalInvalid("Unknown proposal")
    function = proposal.get("wsfunction")
    if not isinstance(function, str) or function not in ALLOWED_FUNCTIONS or proposal.get("destructive") is not (function in DESTRUCTIVE_FUNCTIONS):
        raise ProposalInvalid("Operation is not permitted")
    if function == "core_user_update_users" and _is_suspension(proposal.get("params")):
        pass  # exactly one user, only the suspended flag
    elif function == "core_user_update_users":
        params = proposal.get("params")
        if not isinstance(params, dict) or set(params) != {"standard_password_reset"}:
            raise ProposalInvalid("Only standard password reset or suspension changes are permitted")
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
    if function == STUDENT_BATCH_FUNCTION:
        _validate_student_batch(proposal["params"])
    if function == CONFIRM_USERS_FUNCTION:
        userids = proposal["params"].get("userids")
        if (set(proposal["params"]) != {"userids"} or not isinstance(userids, list)
                or not 0 < len(userids) <= CONFIRM_USERS_MAX or not all(_positive_id(u) for u in userids)
                or len(set(userids)) != len(userids)):
            raise ProposalInvalid("Invalid account confirmation")
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
