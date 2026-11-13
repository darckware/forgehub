"""The owner's list describes a suspension or an account confirmation from the hashed params,
so an agent's summary saying "Liberar" can never sit unnoticed on a `suspended: 1`."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.routes import moodle_approval as _route
from app.core.moodle_proposal_verification import _canonical
from app.tests.test_moodle_telegram_decision import client, request_row  # noqa: F401

ORIGINAL_SOURCE = _route._source


def _proposal(request_id, wsfunction, params, summary):
    now = datetime.now(timezone.utc)
    data = {"request_id": request_id, "wsfunction": wsfunction, "params": params, "destructive": False,
            "status": "pending", "environment": "staging", "host": "moodle.test:9443", "summary": summary,
            "created_at": (now - timedelta(minutes=1)).isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat()}
    material = [wsfunction, params, data["environment"], data["host"]]
    data["params_hash"] = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    return data


@pytest.mark.parametrize(("wsfunction", "params", "expected"), [
    ("core_user_update_users", {"users": [{"id": 11, "suspended": 1}]}, {"kind": "suspend_user", "user_id": 11}),
    ("core_user_update_users", {"users": [{"id": 11, "suspended": 0}]}, {"kind": "reactivate_user", "user_id": 11}),
    ("local_moodle_accounts_confirm_users", {"userids": [30, 31]}, {"kind": "confirm_accounts", "user_ids": [30, 31]}),
])
async def test_the_owner_list_carries_the_generated_operation_view(client, request_row, tmp_path, monkeypatch,  # noqa: F811
                                                                   wsfunction, params, expected):
    from sqlalchemy import select

    from app.core.security import create_access_token
    from app.db.base import AsyncSessionLocal
    from app.db.models.moodle_approval import MoodleApproval
    from app.db.models.user import User

    async with AsyncSessionLocal() as db:
        link = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == request_row["message_id"]))
        request_id = str(link.request_id)
        data = _proposal(request_id, wsfunction, params, "Liberar o acesso do aluno")
        link.params_hash = data["params_hash"]
        user = await db.get(User, request_row["owner_id"])
        headers = {"Authorization": f"Bearer {create_access_token(user.username)}"}
        await db.commit()
    (tmp_path / "p.json").write_text(json.dumps({"proposals": {request_id: data}}), encoding="utf-8")
    monkeypatch.setattr(_route, "_source", ORIGINAL_SOURCE)
    listed = (await client.get("/api/v1/personal/moodle-approvals", headers=headers)).json()
    item = next(entry for entry in listed["items"] if entry["request_id"] == request_id)
    assert item["operation_view"] == expected
    assert item["summary"] == "Liberar o acesso do aluno" and item["batch"] is None
    assert uuid.UUID(item["message_id"]) == request_row["message_id"]
