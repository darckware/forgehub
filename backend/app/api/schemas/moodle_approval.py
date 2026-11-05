import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ApprovalItem(BaseModel):
    request_id: uuid.UUID
    message_id: uuid.UUID
    params_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    message_updated_at: datetime


class DecisionBatch(BaseModel):
    items: list[ApprovalItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_items(self):
        if len({x.request_id for x in self.items}) != len(self.items) or len({x.message_id for x in self.items}) != len(self.items):
            raise ValueError("Duplicate proposal or message")
        if any(x.message_updated_at.tzinfo is None for x in self.items):
            raise ValueError("Message timestamps require timezone")
        return self


class AuthorizeIn(DecisionBatch):
    executor_agent_id: uuid.UUID
    instruction: str = Field(max_length=4000)


class RejectIn(DecisionBatch):
    reason: str | None = Field(default=None, max_length=1000)


class RegisterIn(BaseModel):
    request_id: uuid.UUID


class ClaimIn(BaseModel):
    request_id: uuid.UUID
    message_id: uuid.UUID
    params_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class StatusIn(BaseModel):
    request_id: uuid.UUID
    message_id: uuid.UUID


class TelegramDecisionIn(BaseModel):
    message_id: uuid.UUID
    action: Literal["approve", "reject"]
    telegram_user_id: int


class FinishIn(BaseModel):
    request_id: uuid.UUID
    message_id: uuid.UUID
    outcome: Literal["completed", "failed", "uncertain"]
