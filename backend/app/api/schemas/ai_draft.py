"""Request/response shapes for the cross-phase "Gerar via IA" draft endpoint.

These models are NOT persisted entities -- they only describe (a) what the
frontend asks for and (b) the shape an agent's JSON reply must match for a
given `target_kind` before it's shown to the human for review. Applying a
draft (creating the actual System Element / Planning Item / Task / concept
fields) always goes through the domain's own existing, already-permissioned
endpoints -- see core/ai_draft.py's module docstring for why.
"""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AiDraftTargetKind = Literal[
    "concept", "system_elements", "planning_items", "tasks", "review", "tech_stack", "context_summary",
]


class AiDraftRequest(BaseModel):
    agent_id: uuid.UUID
    target_kind: AiDraftTargetKind
    context: str = Field(default="", max_length=100_000)
    extra_instruction: str = Field(default="", max_length=10_000)
    # Lets target_kind="review" (and, later, others) load real current state
    # server-side instead of trusting only client-supplied context -- e.g. a
    # ProductConcept id. Meaning depends on target_kind; optional everywhere.
    subject_id: uuid.UUID | None = None


class TechStackDraftItem(BaseModel):
    layer: Literal["frontend", "backend", "database", "deploy_infra"]
    # Nullable on purpose: an agent asked for all 4 layers legitimately has
    # no opinion for some (e.g. a headless automation has nothing to say
    # about "frontend") -- observed in practice returning decision=null
    # rather than omitting the layer entirely. The caller (apply step) skips
    # null-decision entries instead of this being a shape violation.
    decision: str | None = Field(default=None, min_length=1, max_length=255)
    rationale: str | None = None


class ConceptDraft(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    problem_statement: str = Field(min_length=1)
    vision: str | None = None
    scope_summary: str | None = None
    project_description: str | None = None
    tech_stack: list[TechStackDraftItem] = Field(default_factory=list)
    documentation_markdown: str | None = None


class SystemElementDraftItem(BaseModel):
    key: str = Field(min_length=1)
    family: str = Field(min_length=1)
    element_type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None


class SystemRelationDraftItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_key: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)


class SystemElementsDraft(BaseModel):
    elements: list[SystemElementDraftItem] = Field(min_length=1)
    relations: list[SystemRelationDraftItem] = Field(default_factory=list)


class PlanningItemDraftItem(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    item_type: str = Field(min_length=1)
    description: str | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None


class PlanningItemsDraft(BaseModel):
    items: list[PlanningItemDraftItem] = Field(min_length=1)


class TaskDraftItem(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    plan_brief: str | None = None
    suggested_role: Literal["developer", "data_engineer", "release_manager", "qa"] | None = None


class TasksDraft(BaseModel):
    tasks: list[TaskDraftItem] = Field(min_length=1)


class ReviewDraft(BaseModel):
    summary: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    suggested_corrections: list[str] = Field(default_factory=list)


class TechStackDraft(BaseModel):
    tech_stack: list[TechStackDraftItem] = Field(default_factory=list)


class ContextSummaryDraft(BaseModel):
    summary: str = Field(min_length=1)


DRAFT_SCHEMA_BY_KIND: dict[AiDraftTargetKind, type[BaseModel]] = {
    "concept": ConceptDraft,
    "system_elements": SystemElementsDraft,
    "planning_items": PlanningItemsDraft,
    "tasks": TasksDraft,
    "review": ReviewDraft,
    "context_summary": ContextSummaryDraft,
    "tech_stack": TechStackDraft,
}
