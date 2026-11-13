import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core import mission_learning as mod


def data(**changes):
    return mod.LearningEvidence(source_execution_ids=[uuid4()], reproduction='Repeat the isolated verification',
                                lesson='Verify the stored artifact before reporting completion',
                                proposed_skill_version='1.2.0', runtime_types=['codex'], **changes)


@pytest.mark.parametrize('field,value', [('contains_private_context', True), ('changes_authority', True),
                                        ('runtime_types', ['unknown-runtime'])])
def test_private_authority_and_unknown_runtime_cannot_be_promoted(field, value):
    values = dict(source_execution_ids=[uuid4()], reproduction='Synthetic reproduction', lesson='A bounded lesson',
                  proposed_skill_version='1.2.0', runtime_types=['codex'])
    values[field] = value
    with pytest.raises((ValidationError, HTTPException)):
        mod.LearningEvidence(**values)


def test_secret_cannot_be_promoted():
    with pytest.raises((ValidationError, HTTPException)):
        mod.LearningEvidence(source_execution_ids=[uuid4()], reproduction='Synthetic reproduction',
                             lesson='Use agt_123456789012345678901234', proposed_skill_version='1.2.0', runtime_types=['codex'])


def test_verified_execution_without_accepted_reviewed_task_is_only_observation(monkeypatch):
    learning = data()
    db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(task_id=uuid4(), status='verified')))
    monkeypatch.setattr(mod, 'scope_task', AsyncMock(return_value=(SimpleNamespace(status='in_progress'), None)))
    with pytest.raises(HTTPException) as error:
        asyncio.run(mod.validate_learning(db, object(), learning))
    assert error.value.detail['code'] == 'LEARNING_TASK_NOT_ACCEPTED'
