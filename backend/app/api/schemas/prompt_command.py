"""Pydantic schemas for reusable chat prompt commands."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

RESERVED_PROMPT_COMMAND_NAMES = {"model", "status", "help", "version", "title", "profile"}


def normalize_command_name(value: str) -> str:
    name = value.strip().lstrip("/").lower()
    cleaned = []
    prev_dash = False
    for char in name:
        if char.isalnum() or char == "_":
            cleaned.append(char)
            prev_dash = False
        elif char == "-" and not prev_dash:
            cleaned.append(char)
            prev_dash = True
        elif not prev_dash:
            cleaned.append("-")
            prev_dash = True
    return "".join(cleaned).strip("-")[:32]


class PromptCommandBase(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=240)
    prompt: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = normalize_command_name(value)
        if not normalized:
            raise ValueError("name must contain letters, numbers, hyphen or underscore")
        if normalized in RESERVED_PROMPT_COMMAND_NAMES:
            raise ValueError(f"/{normalized} is reserved by Hermes")
        return normalized

    @field_validator("description", "prompt")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class PromptCommandCreate(PromptCommandBase):
    pass


class PromptCommandUpdate(PromptCommandBase):
    pass


class PromptCommandOut(PromptCommandBase):
    id: str
    created_at: datetime
    updated_at: datetime
