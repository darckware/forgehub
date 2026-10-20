"""Public representation of an Aegis prompt-improvement technique."""
from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImprovePromptRequest(BaseModel):
    draft: str = Field(min_length=1, max_length=100_000)
    instruction: str = Field(default="", max_length=10_000)
    technique_code: str = Field(default="automatic", min_length=1, max_length=64)

    @field_validator("draft", "instruction", "technique_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class PromptTechniqueRecommendRequest(BaseModel):
    draft: str = Field(min_length=1, max_length=100_000)


class PromptTechniqueRecommendationOut(BaseModel):
    technique_code: str
    score: int
    matched_terms: list[str]


class PromptTechniqueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    category: str
    name: str
    summary: str
    when_to_use: str
    when_to_avoid: str | None
    requirements: list[str]
    compatible_with: list[str]
    conflicts_with: list[str]
    example: str | None
    effort: str
    selection_mode: str
    template_version: int
    sort_order: int
    is_builtin: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
