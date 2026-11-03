import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from app.api.schemas.moodle_approval import AuthorizeIn


def test_batch_rejects_duplicate_proposals():
    item = {"request_id": str(uuid.uuid4()), "message_id": str(uuid.uuid4()),
            "params_hash": "a" * 64, "message_updated_at": datetime.now(timezone.utc)}
    with pytest.raises(ValidationError):
        AuthorizeIn(password="secret", telegram_challenge="proof", executor_agent_id=uuid.uuid4(),
                    instruction="test", items=[item, item])
