"""Additive intent bound to the existing immutable Work Package."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings


class RuntimeSkillRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    version: str = Field(min_length=1, max_length=50)
    required: bool = True


class RuntimeIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['forge-runtime-intent/v1'] = 'forge-runtime-intent/v1'
    strategy: Literal['native', 'single', 'delegate'] = 'native'
    max_children: int = Field(default=0, ge=0, le=3)
    skills: list[RuntimeSkillRequirement] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def bounded_strategy(self):
        if self.strategy != 'native' and not settings.NATIVE_DELEGATION_ENABLED:
            # Native sub-agent strategies are off until NATIVE_DELEGATION_ENABLED.
            raise ValueError(f"strategy '{self.strategy}' requires NATIVE_DELEGATION_ENABLED")
        if (self.strategy != 'delegate') != (self.max_children == 0):
            raise ValueError('single requires zero children; delegate requires a positive child limit')
        if len({s.name for s in self.skills}) != len(self.skills):
            raise ValueError('skill names must be unique')
        return self
