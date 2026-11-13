"""Pydantic schemas for mission phases (docs/architecture/MISSION_PHASES_PLAN.md).

``idempotency_key`` is optional for a person (the screen) and required for an
agent (the §0.4 receipt, like every M0.2 command); the route enforces it.
``expected_phase_status``, when sent, guards against acting on a phase that
moved meanwhile (409 PHASE_STATE_CHANGED).
"""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.mission import PHASE_STATUSES

Key = Field(default=None, min_length=1, max_length=150)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Key


class PhaseCreateIn(_In):
    name: str = Field(min_length=1, max_length=120)
    objective: str | None = Field(default=None, max_length=20000)


class PhaseUpdateIn(_In):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    objective: str | None = Field(default=None, max_length=20000)


class PhasesReorderIn(_In):
    phase_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class PlanningsReorderIn(_In):
    planning_item_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class TasksSequenceIn(_In):
    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class HomologationRequestIn(_In):
    homologator_agent_id: uuid.UUID
    # Re-send a phase already `homologating` (the previous homologation task
    # is withdrawn if it has not started; a run in flight refuses).
    replace: bool = False
    expected_phase_status: Literal[PHASE_STATUSES] | None = None  # type: ignore[valid-type]


class HomologationReportIn(_In):
    verdict: Literal["approved", "rejected"]
    summary: str = Field(min_length=1, max_length=20000)
    # git:/file:/url refs; stored as text, one per line.
    evidence: list[str] = Field(default_factory=list, max_length=50)


class PhaseApproveIn(_In):
    reason: str | None = Field(default=None, max_length=4000)
    expected_phase_status: Literal[PHASE_STATUSES] | None = None  # type: ignore[valid-type]


class PhaseReturnIn(_In):
    reason: str = Field(min_length=1, max_length=4000)
    expected_phase_status: Literal[PHASE_STATUSES] | None = None  # type: ignore[valid-type]
