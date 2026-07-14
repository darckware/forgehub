"""Contracts for the shared agent-controlled Workspace browser."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkspaceBrowserPointerState(BaseModel):
    x: float
    y: float
    at: str


class WorkspaceBrowserStateOut(BaseModel):
    running: bool
    cdp_url: str
    url: str
    title: str
    ready_state: str
    viewport_width: int
    viewport_height: int
    image_base64: str | None = None
    captured_at: str
    last_pointer: WorkspaceBrowserPointerState | None = None


class WorkspaceBrowserStart(BaseModel):
    url: str = "about:blank"


class WorkspaceBrowserNavigate(BaseModel):
    url: str


class WorkspaceBrowserPointer(BaseModel):
    x: float = Field(ge=0, le=10_000)
    y: float = Field(ge=0, le=10_000)
    end_x: float | None = Field(default=None, ge=0, le=10_000)
    end_y: float | None = Field(default=None, ge=0, le=10_000)


class WorkspaceBrowserText(BaseModel):
    text: str = Field(max_length=10_000)


class WorkspaceBrowserScroll(BaseModel):
    x: float = Field(ge=0, le=10_000)
    y: float = Field(ge=0, le=10_000)
    delta_y: float = Field(ge=-5_000, le=5_000)


class WebAutomationStep(BaseModel):
    action: Literal["navigate", "click", "type", "select", "press", "scroll", "wait", "assert_text"]
    selector: str | None = Field(default=None, max_length=1000)
    value: str | None = Field(default=None, max_length=10_000)
    url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    delta_y: int | None = Field(default=None, ge=-5000, le=5000)
    wait_ms: int | None = Field(default=None, ge=0, le=30_000)

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == "navigate" and not self.url:
            raise ValueError("navigate requires url")
        if self.action in {"click", "type", "select"} and not self.selector:
            raise ValueError(f"{self.action} requires selector")
        if self.action in {"type", "select", "press", "assert_text"} and self.value is None:
            raise ValueError(f"{self.action} requires value")
        return self


class WebAutomationRoutineCreate(BaseModel):
    product_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[WebAutomationStep] = Field(min_length=1, max_length=100)


class WebAutomationRoutineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[WebAutomationStep] | None = Field(default=None, min_length=1, max_length=100)


class WebAutomationRoutineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    description: str | None
    steps: list[WebAutomationStep]
    created_at: datetime
    updated_at: datetime


class WebAutomationRunOut(BaseModel):
    routine_id: uuid.UUID
    status: str
    steps: list[dict]
    browser: WorkspaceBrowserStateOut
