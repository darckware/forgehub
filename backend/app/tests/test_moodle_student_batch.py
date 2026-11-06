"""One Moodle approval covers a whole student batch. The fixture is a real proposal of the MCP,
with fictitious data, so a change in either hash or shape fails here."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.api.routes import moodle_approval as _route
from app.core.moodle_proposal_verification import ProposalInvalid, _canonical, student_batch_view, validate_proposal
from app.tests.test_moodle_telegram_decision import client, request_row  # noqa: F401

ORIGINAL_SOURCE = _route._source

FIXTURE = Path(__file__).parent / "fixtures" / "moodle_student_batch_proposal.json"


def proposal():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    data["created_at"] = (now - timedelta(minutes=1)).isoformat()
    data["expires_at"] = (now + timedelta(hours=1)).isoformat()
    return data


def rehash(data):
    material = [data["wsfunction"], data["params"], data["environment"], data["host"]]
    data["params_hash"] = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    return data


def rows(data):
    return data["params"]["student_batch"]["rows"]


def test_accepts_the_proposal_the_mcp_signed_with_accents_and_suffix():
    data = proposal()
    assert validate_proposal(data, data["request_id"]) is data


def test_a_row_changed_after_the_hash_is_refused():
    data = proposal()
    rows(data)[0]["enrolment"]["groupid"] = 99
    with pytest.raises(ProposalInvalid, match="integrity"):
        validate_proposal(data, data["request_id"])


def test_a_password_is_refused_even_with_a_correct_hash():
    for change in (lambda r: r["account"].__setitem__("password", "x"), lambda r: r.__setitem__("password", "x"),
                   lambda r: r["account"].__setitem__("firstname", "@Semed17012014")):
        data = proposal()
        change(rows(data)[0])
        with pytest.raises(ProposalInvalid):
            validate_proposal(rehash(data), data["request_id"])


@pytest.mark.parametrize("change", [
    lambda r: r["account"].__setitem__("lastname", "OUTRO"),
    lambda r: r["account"].__setitem__("email", "real@example.org"),
    lambda r: r["account"].__setitem__("auth", "ldap"),
    lambda r: r["account"]["standard_password"].__setitem__("date_of_birth", "31/02/2014"),
    lambda r: r["account"]["standard_password"].__setitem__("policy", "outra"),
    lambda r: r["enrolment"].__setitem__("role_shortname", "editingteacher"),
    lambda r: r.__setitem__("extra", 1),
])
def test_a_row_outside_the_contract_is_refused(change):
    data = proposal()
    change(rows(data)[0])
    with pytest.raises(ProposalInvalid):
        validate_proposal(rehash(data), data["request_id"])


def test_more_rows_than_the_run_fits_are_refused():
    data = proposal()
    base = rows(data)[0]
    data["params"]["student_batch"]["rows"] = [{**copy.deepcopy(base), "row": n} for n in range(100, 131)]
    with pytest.raises(ProposalInvalid, match="size"):
        validate_proposal(rehash(data), data["request_id"])


def test_a_repeated_username_is_refused():
    data = proposal()
    second = copy.deepcopy(rows(data)[0])
    second["row"] = 99
    rows(data).append(second)
    with pytest.raises(ProposalInvalid, match="Repeated"):
        validate_proposal(rehash(data), data["request_id"])


def test_the_view_shows_what_marcelo_checks_and_never_the_birth_date():
    data = proposal()
    view = student_batch_view(data["params"])
    assert (view["total"], view["new_accounts"], view["existing"], view["account_only"]) == (6, 5, 1, 1)
    first = view["rows"][0]
    assert (first["full_name"], first["firstname"], first["lastname"]) == ("ANA LUÍSA DOS REIS", "ANA", "LUÍSA DOS REIS")
    assert first["username"] == "analuisa17012014" and first["email"] == "analuisa17012014@gmail.com"
    assert first["corrected_fields"] == ["firstname"]
    assert [row["username"] for row in view["rows"]][1:3] == ["joaosilva15092012", "joaosilva15092012_2"]
    assert view["rows"][3]["account_only"] is True
    assert view["rows"][4]["possible_duplicate_of"] == [{"id": 61, "username": "duda01012001"}]
    assert view["held_rows"][0]["candidates"] == [{"id": 60, "username": "caioreis01012001"}]
    assert view["rejected_rows"][0]["code"] == "single_word_name"
    assert "17/01/2014" not in json.dumps(view, ensure_ascii=False) and "date_of_birth" not in json.dumps(view)


async def test_a_wrong_hash_answers_409_and_the_owner_list_hides_the_birth_date(client, request_row, tmp_path, monkeypatch):
    from app.api.routes import moodle_approval
    from app.core.security import create_access_token
    from app.db.base import AsyncSessionLocal
    from app.db.models.moodle_approval import MoodleApproval
    from app.db.models.user import User
    from sqlalchemy import select

    data = proposal()
    async with AsyncSessionLocal() as db:
        link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == request_row["message_id"]))
        link.params_hash = data["params_hash"]
        request_id = str(link.request_id)
        user = await db.get(User, request_row["owner_id"])
        headers = {"Authorization": f"Bearer {create_access_token(user.username)}"}
        await db.commit()
    data["request_id"] = request_id
    (tmp_path / "p.json").write_text(json.dumps({"proposals": {request_id: data}}), encoding="utf-8")
    monkeypatch.setattr(moodle_approval, "_source", ORIGINAL_SOURCE)
    url = "/api/v1/personal/moodle-approvals"
    listed = (await client.get(url, headers=headers)).json()
    item = next(entry for entry in listed["items"] if entry["request_id"] == request_id)
    assert item["batch"]["total"] == 6 and item["params"] == {}
    assert "17/01/2014" not in json.dumps(listed, ensure_ascii=False)
    body = {"executor_agent_id": str(request_row["agent_id"]), "instruction": "", "items": [{
        "request_id": request_id, "message_id": item["message_id"], "params_hash": data["params_hash"],
        "message_updated_at": item["message_updated_at"]}]}
    rows(data)[0]["enrolment"]["groupid"] = 99  # The file changes after the owner read it.
    (tmp_path / "p.json").write_text(json.dumps({"proposals": {request_id: data}}), encoding="utf-8")
    assert (await client.post(f"{url}/authorize", headers=headers, json=body)).status_code == 409
    rows(data)[0]["enrolment"]["groupid"] = 7
    (tmp_path / "p.json").write_text(json.dumps({"proposals": {request_id: data}}), encoding="utf-8")
    assert (await client.post(f"{url}/authorize", headers=headers, json=body)).status_code == 200
