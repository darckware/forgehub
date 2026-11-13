"""Evidence-qualified learning proposals; never a memory or authority registry."""
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.maintenance_proposals import refuse_literal_secret
from app.core.mission import mission_error
from app.db.models.task import TaskExecution


class LearningEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_execution_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    reproduction: str = Field(min_length=10, max_length=4000)
    lesson: str = Field(min_length=10, max_length=4000)
    proposed_skill_version: str = Field(pattern=r'^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$')
    runtime_types: list[Literal['claude', 'codex', 'agy', 'hermes']] = Field(min_length=1, max_length=4)
    contains_private_context: Literal[False] = False
    changes_authority: Literal[False] = False

    @model_validator(mode='after')
    def promotion_boundary(self):
        text = self.reproduction + '\n' + self.lesson
        refuse_literal_secret(text)
        if re.search(r'\b(grant|authorize|autorizar|conceder)\b|skip.{0,20}(approval|permission)|ignore.{0,20}(approval|permission)', text, re.I):
            raise ValueError('A learning proposal cannot grant authority or bypass approval')
        if len(set(self.source_execution_ids)) != len(self.source_execution_ids):
            raise ValueError('Learning source executions must be distinct')
        return self


async def scope_task(db, mission, task_id):
    from app.api.routes.mission_task import _scope_task
    return await _scope_task(db, mission, task_id)


async def validate_learning(db, mission, learning):
    from app.core.task_completion_guard import CompletionRefused, evaluate_task_completion
    proofs = []
    for execution_id in learning.source_execution_ids:
        execution = await db.get(TaskExecution, execution_id)
        if execution is None or execution.status != 'verified':
            raise mission_error(422, 'LEARNING_EXECUTION_UNVERIFIED', 'Learning must cite verified canonical executions')
        task, _project_id = await scope_task(db, mission, execution.task_id)
        if task.status not in {'done', 'deployed'}:
            raise mission_error(422, 'LEARNING_TASK_NOT_ACCEPTED', 'Learning sources must have accepted, independently reviewed tasks')
        try:
            # Re-use the live evidence verifier and independent-review guard.
            proof = await evaluate_task_completion(db, task, 'done')
        except CompletionRefused as exc:
            raise mission_error(422, 'LEARNING_EVIDENCE_UNQUALIFIED', 'Learning source failed current evidence or independent review checks') from exc
        if proof.execution_id != execution_id:
            raise mission_error(422, 'LEARNING_EXECUTION_SUPERSEDED', 'Learning must cite the currently accepted execution')
        proofs.append(proof.as_payload())
    return {'evidence': learning.model_dump(mode='json'), 'proofs': proofs,
            'status': 'evidence_verified_owner_review_pending', 'publication': 'not_published',
            'authority_changed': False}
