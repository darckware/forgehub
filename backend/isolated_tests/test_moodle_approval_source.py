import json
import uuid

import pytest
from fastapi import HTTPException

from app.api.routes.moodle_approval import _source
from app.core.config import settings
from test_moodle_proposal_verification import proposal


def test_source_store_is_bound_to_registered_agent_and_detects_tampering(tmp_path, monkeypatch):
    source, other = uuid.uuid4(), uuid.uuid4()
    p = proposal()
    path = tmp_path / "proposals.json"
    path.write_text(json.dumps({"proposals": {p["request_id"]: p}}))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_ENABLED", True)
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_OWNER_ID", str(uuid.uuid4()))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_WORKING_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_SOURCE_FILES", json.dumps({str(source): str(path)}))
    assert _source(source, uuid.UUID(p["request_id"]))["params_hash"] == p["params_hash"]
    with pytest.raises(HTTPException) as exc:
        _source(other, uuid.UUID(p["request_id"]))
    assert exc.value.status_code == 403
    p["params"]["userids"] = [13]
    path.write_text(json.dumps({"proposals": {p["request_id"]: p}}))
    with pytest.raises(HTTPException) as exc:
        _source(source, uuid.UUID(p["request_id"]))
    assert exc.value.status_code == 409
