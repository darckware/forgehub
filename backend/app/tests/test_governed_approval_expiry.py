"""An expired approval request must stay expired after the 409.

Before 2026-10-12 the status change was only staged on the session; the
HTTPException rolled it back and the request stayed "pending" forever.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.governed_approval import decide_concept_approval, decide_task_approval


class _Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.parametrize("decide", [decide_concept_approval, decide_task_approval])
async def test_expired_request_is_persisted_before_refusal(decide):
    db = _Session()
    request = SimpleNamespace(
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    with pytest.raises(HTTPException) as exc:
        await decide(db, None, request, "approved", None, None)

    assert exc.value.status_code == 409
    assert request.status == "expired"
    assert db.commits == 1
